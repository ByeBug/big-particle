import time
import queue
import threading
import os
import shutil
import logging
from datetime import datetime
from typing import Optional, Deque
from collections import deque

from .delayed_queue import DelayedQueue
from .decoder import DecoderFactory
from .logging_utils import StreamLoggerAdapter
from .frame import DecodedFrame
from .count_down_latch import CountDownLatch
from .algorithm.status import InferStatus
from .algorithm.big_particle_algo import BigParticleAlgo
from django.db import transaction

logger = logging.getLogger(__name__)


class VideoStreamProcessor:
    """视频流处理器：包含解码、推理、编码三个线程"""
    
    ENCODE_DELAY_SEC = 0.5  # 编码延迟时间（秒）

    # 控制是否启用推理和编码，暂时关闭
    ENABLE_INFER = True
    ENABLE_ENCODE = False
    ENABLE_SAVE = True  # 启用帧保存功能

    SAVE_FRAMES_DIR = "/data/big-particle-data/storage/saved_frames"
    SAFE_FREE_SPACE_GB = 100  # 安全剩余空间阈值（GB）
    
    # 算法配置
    ALGORITHM_CONFIGS = {
        'big_particle': {
            'enabled': True,
            'infer_interval_ms': 100,  # 推理间隔100ms
            'model_path': '/home/zhaosiyuan/dev/big-particle/backend/paddle_samples/models/big_particle_trt',
            'batch_size': 8,
            'threshold': 0.5,      # 模型阈值
            'size_threshold': 28,  # 粒径阈值（毫米）
        }
    }
    
    def __init__(self, video_stream):
        self.video_stream = video_stream
        # 视频流不需要设置采集帧率，为构建队列，预设为 30
        self.fps = video_stream.fps or 30
        
        # 设置带 StreamID 的日志器
        self.logger = StreamLoggerAdapter(logger, {'stream_id': video_stream.id})
        
        # 队列设置
        self.infer_queue: queue.Queue[DecodedFrame] = queue.Queue(maxsize=self.fps)
        # 编码队列大小 = fps * (延迟时间 + 缓冲时间)
        encode_queue_size = int(self.fps * (self.ENCODE_DELAY_SEC + 1))
        self.encode_queue = DelayedQueue(delay_seconds=self.ENCODE_DELAY_SEC, maxsize=encode_queue_size)
        # 保存队列，缓冲大小为 fps 的 2 倍
        self.save_queue = queue.Queue(maxsize=self.fps * 2)
        
        # 最新帧缓存，使用 deque 实现循环队列，最大长度为 2
        self.latest_frame_cache: Deque[DecodedFrame] = deque(maxlen=2)
        
        # 线程
        self.decode_thread = None
        self.infer_thread = None
        self.encode_thread = None
        self.save_thread = None
        
        # 控制标志
        self.running = False
        self._stop_save_thread = False  # 专门控制保存线程的停止
        self._stop_event = threading.Event()  # 停止事件，用于可中断等待
        
        # Decoder 相关
        self.decoder = None
        self.decoder_valid = False
        self._last_fps_log_time = time.time()  # 上次打印帧率的时间
        
        # 算法实例和推理时间控制
        self.algorithms = []  # 算法实例列表
        self.next_infer_times = {}  # 每种算法的下次推理时间 {algorithm_type: next_time_ms}
        self._init_algorithms()
    
    def start(self):
        """启动所有处理线程"""
        if self.running:
            self.logger.warning("视频流处理器已启动")
            return
        
        self.logger.info("启动视频流处理器")
        self.running = True
        
        # TODO decode 线程中，decoder 有效则创建推理和编码线程；无效则停止推理和编码线程
        self.decode_thread = threading.Thread(target=self.decode_loop, name=f"decode-{self.video_stream.id}")
        if self.ENABLE_INFER:
            self.infer_thread = threading.Thread(target=self.infer_loop, name=f"infer-{self.video_stream.id}")
        if self.ENABLE_ENCODE:
            self.encode_thread = threading.Thread(target=self.encode_loop, name=f"encode-{self.video_stream.id}")
        if self.ENABLE_SAVE and self.video_stream.save_frames:
            self.save_thread = threading.Thread(target=self.save_loop, name=f"save-{self.video_stream.id}")
        
        self.decode_thread.start()
        if self.ENABLE_INFER:
            self.infer_thread.start()
        if self.ENABLE_ENCODE:
            self.encode_thread.start()
        if self.ENABLE_SAVE and self.video_stream.save_frames:
            self.save_thread.start()
    
    def stop(self):
        """停止所有处理线程"""
        # TODO 关闭流内的所有算法实例。算法实例关闭时释放对 model 的引用。model 引用为 0 时释放
        self.logger.info("停止视频流处理器")
        self.running = False
        self._stop_event.set()  # 触发停止事件，中断等待
        
        # 等待所有线程正常结束
        threads = [self.decode_thread]
        if self.ENABLE_INFER:
            threads.append(self.infer_thread)
        if self.ENABLE_ENCODE:
            threads.append(self.encode_thread)
        if self.ENABLE_SAVE and self.save_thread:
            threads.append(self.save_thread)
        for thread in threads:
            if thread and thread.is_alive():
                thread.join(timeout=5.0)  # 最多等待5秒
                if thread.is_alive():
                    self.logger.warning(f"线程 {thread.name} 未能在5秒内正常结束")
    
    def decode_loop(self):
        """解码线程：读取视频帧并分发到推理和编码队列"""
        while self.running:
            # 如果 decoder 无效，尝试创建和打开
            if not self.decoder_valid:
                self._init_decoder()
                if not self.decoder_valid:
                    # 创建或打开失败，更新状态并等待 30 秒后重试
                    self.logger.warning("Decoder 创建失败，30秒后重试...")
                    message = 'Decoder 打开失败'
                    if self.video_stream.status != 'abnormal' or self.video_stream.status_message != message:
                        self._update_stream_status('abnormal', message)
                    if self._stop_event.wait(timeout=30):  # 等待停止事件，最多30秒
                        break  # 收到停止信号，退出循环
                    continue
                else:
                    # 成功初始化 decoder，更新状态和流信息到数据库
                    if self.video_stream.status != 'normal':
                        self._update_stream_status('normal', '')
                    self._update_stream_info(
                        width=self.decoder.width,
                        height=self.decoder.height,
                        fps=self.decoder.fps
                    )
            
            try:
                # 使用实际的 decoder 获取帧（内置时间控制）
                frame = self.decoder.get_frame_with_timing()
                if frame is None:
                    time.sleep(0.01)
                    continue
                
                # 将帧加入最新帧缓存（循环队列，自动保留最新的2帧）
                self.latest_frame_cache.append(frame)

                # 每 30 秒打印一次帧率统计
                current_time = time.time()
                if current_time - self._last_fps_log_time >= 30:
                    self.logger.info(f"已解码 {self.decoder.get_frame_count()} 帧，当前帧率: {self.decoder.get_actual_fps()}")
                    self._last_fps_log_time = current_time
                
                # 尝试加入推理队列
                try:
                    if self.ENABLE_INFER:
                        self.infer_queue.put_nowait(frame)
                        self._submit_to_algorithms(frame)
                except queue.Full:
                    # TODO 添加推理队列满 metric
                    pass  # 推理队列满，丢弃帧
                
                # 尝试加入编码队列
                try:
                    if self.ENABLE_ENCODE:
                        self.encode_queue.put_nowait(frame)
                except queue.Full:
                    # TODO 添加编码队列满 metric
                    pass  # 编码队列满，丢弃帧
                
                # 尝试加入保存队列
                try:
                    if self.ENABLE_SAVE and self.video_stream.save_frames:
                        self.save_queue.put_nowait(frame)
                except queue.Full:
                    # TODO 添加保存队列满 metric
                    pass  # 保存队列满，丢弃帧
                
            except Exception as e:
                # 关闭 decoder 并标记为无效，等待30秒
                self.logger.exception(f"解码异常，30秒后重试")
                self._update_stream_status('abnormal', f'解码异常: {str(e)}')
                try:
                    self.decoder.close()
                except Exception as close_error:
                    self.logger.exception(f"关闭解码器时出错")
                self.decoder = None
                self.decoder_valid = False
                if self._stop_event.wait(timeout=30):  # 等待停止事件，最多30秒
                    break  # 收到停止信号，退出循环
        
        try:
            if self.decoder:
                self.decoder.close()
                self.decoder = None
                self.decoder_valid = False
        except Exception as e:
            self.logger.error(f"关闭解码器时出错: {e}")
        self.logger.info("解码线程退出")
    
    def _init_algorithms(self):
        """初始化算法实例"""
        for algo_name, algo_config in self.ALGORITHM_CONFIGS.items():
            if algo_config.get('enabled', False):
                try:
                    self.logger.info(f"初始化算法: {algo_name}")
                    algo_config['name'] = algo_name
                    if algo_name == 'big_particle':
                        algo_instance = BigParticleAlgo(self.video_stream.id, algo_config)
                        self.algorithms.append(algo_instance)
                    # 初始化下次推理时间为 -1
                    self.next_infer_times[algo_name] = -1
                except Exception as e:
                    self.logger.error(f"初始化算法 {algo_name} 失败: {e}")
                    continue
        
        self.logger.info(f"共初始化 {len(self.algorithms)} 个算法")
    
    def _init_decoder(self):
        """初始化 decoder：创建并打开"""
        try:
            # 使用工厂模式创建 decoder
            self.decoder = DecoderFactory.create_decoder(self.video_stream)
            
            # 尝试打开 decoder
            if self.decoder.open():
                self.decoder_valid = True
                self.logger.info(f"Decoder 初始化成功: {self.video_stream.type} - {self.video_stream.address}")
            else:
                self.logger.error(f"Decoder 打开失败: {self.video_stream.type} - {self.video_stream.address}")
                self.decoder.close()
                self.decoder = None
                self.decoder_valid = False
                
        except Exception as e:
            self.logger.error(f"Decoder 初始化异常: {e}")
            self.decoder = None
            self.decoder_valid = False
    
    def _submit_to_algorithms(self, frame: DecodedFrame):   
        """根据算法的推理间隔设置帧的算法状态，并提交帧到算法"""
        frame_timestamp = frame.timestamp  # 毫秒时间戳
        
        # 初始化 CountDownLatch
        frame.algo_latch = CountDownLatch(len(self.algorithms))
        
        for algo_instance in self.algorithms:
            try:
                algo_name = algo_instance.name
                next_infer_time = self.next_infer_times[algo_name]
                
                # 比较帧时间戳和下次推理时间，有 5ms 的 offset，避免解码提前
                if frame_timestamp >= next_infer_time - 5 :
                    # 需要推理
                    frame.algo_status[algo_name] = InferStatus.NEED_INFER
                    infer_interval = self.ALGORITHM_CONFIGS[algo_name]['infer_interval_ms']
                    if next_infer_time == -1:
                        # 第一次推理，以帧时间戳为基础
                        self.next_infer_times[algo_name] = frame_timestamp + infer_interval
                    else:
                        # 以上次的下次推理时间为基础
                        self.next_infer_times[algo_name] = next_infer_time + infer_interval
                    
                    self.logger.debug(f"算法 {algo_name} 需要推理, 下次推理时间: {self.next_infer_times[algo_name]}")
                else:
                    # 需要渲染
                    frame.algo_status[algo_name] = InferStatus.NEED_RENDER
                    self.logger.debug(f"算法 {algo_name} 需要渲染")
                
                # 提交帧到算法
                algo_instance.submit(frame)
            except Exception as e:
                self.logger.error(f"提交帧到算法 {algo_name} 失败: {e}")
                # 提交到某个算法失败也要 count down，避免死锁
                frame.algo_latch.count_down()

    def infer_loop(self):
        """推理线程：处理推理队列中的帧"""
        while self.running:
            try:
                frame = self.infer_queue.get(timeout=1.0)
                
                # 等待所有算法完成处理
                if not frame.algo_latch.wait(timeout=1.0):
                    # TODO 添加推理超时 metric
                    self.logger.warning(f"帧处理超时: frame={frame.frame_number}, 剩余算法数={frame.algo_latch.get_count()}")
                else:
                    self.logger.debug(f"帧处理完成: frame={frame.frame_number}")
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"推理线程错误: {e}")
        
        self.logger.info("推理线程退出")
    
    def encode_loop(self):
        """编码线程：处理编码队列中的帧（自动延时500ms）"""
        while self.running:
            try:
                frame = self.encode_queue.get()
                # TODO: 实现实际的编码逻辑
                self.encode_frame(frame)
            except Exception as e:
                self.logger.error(f"编码线程错误: {e}")
        
        self.logger.info("编码线程退出")
    
    def encode_frame(self, frame):
        """编码一帧数据"""
        # TODO: 实现编码逻辑，输出编码后的视频流，帧有 canvas 则用 canvas 编码，否则用 ocv_image 编码
        # print(f"编码处理: {frame}")  # 高频日志，暂时注释
        time.sleep(0.05)  # 模拟编码时间
    
    def save_loop(self):
        """保存线程：保存帧到磁盘，每5分钟创建新文件夹"""
        save_dir = None
        frame_count = 0
        
        while self.running and not self._stop_save_thread:
            try:
                frame = self.save_queue.get(timeout=1.0)
                frame_count += 1
                
                # 每500帧检查一次是否需要创建新的5分钟文件夹
                if frame_count % 500 == 1 or save_dir is None:
                    now = datetime.now()
                    # 每5分钟创建一个文件夹，向下取整到5分钟的倍数
                    minute = now.minute // 5 * 5
                    folder_name = f"{now.strftime('%Y%m%d_%H')}{minute:02d}"
                    save_dir = os.path.join(self.SAVE_FRAMES_DIR, f"stream_{self.video_stream.id}", folder_name)
                    os.makedirs(save_dir, exist_ok=True)
                    self.logger.info(f"创建保存目录: {save_dir}")
                
                # 生成文件名：时间戳
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # 毫秒精度
                filename = f"{timestamp}.png"
                filepath = os.path.join(save_dir, filename)
                
                # 使用 DecodedFrame 的 save 方法保存
                if not frame.save(filepath):
                    self.logger.error(f"保存帧失败: {filepath}")
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"保存线程错误: {e}")
        
        self.logger.info("保存线程退出")

    def get_actual_fps(self) -> int:
        """获取实时帧率"""
        if self.decoder and self.decoder_valid:
            return self.decoder.get_actual_fps()
        return 0
    
    def is_running(self) -> bool:
        """检查处理器是否正在运行"""
        return self.running
    
    def get_latest_frame(self) -> Optional[DecodedFrame]:
        """获取最新的解码帧"""
        if self.latest_frame_cache:
            return self.latest_frame_cache[0]
        return None
    
    def _update_stream_status(self, status: str, message: str = ""):
        """更新数据库中的视频流状态"""
        try:
            with transaction.atomic():
                # 重新从数据库获取最新对象，避免并发修改冲突
                from core.models import VideoStream
                stream = VideoStream.objects.select_for_update().get(id=self.video_stream.id)
                stream.status = status
                stream.status_message = message
                stream.save(update_fields=['status', 'status_message', 'updated_at'])
                # 同步更新内存中的对象
                self.video_stream.status = status
                self.video_stream.status_message = message
        except Exception as e:
            self.logger.error(f"更新视频流状态失败: {e}")
    
    def _update_stream_info(self, width: int = None, height: int = None, fps: int = None):
        """更新数据库中的视频流信息（宽高、fps）"""
        try:
            with transaction.atomic():
                # 重新从数据库获取最新对象，避免并发修改冲突
                from core.models import VideoStream
                stream = VideoStream.objects.select_for_update().get(id=self.video_stream.id)
                
                update_fields = ['updated_at']
                
                if width is not None and width > 0:
                    stream.width = width
                    self.video_stream.width = width
                    update_fields.append('width')
                
                if height is not None and height > 0:
                    stream.height = height
                    self.video_stream.height = height
                    update_fields.append('height')
                
                if fps is not None and fps > 0:
                    stream.fps = fps
                    self.video_stream.fps = fps
                    update_fields.append('fps')
                
                if len(update_fields) > 1:  # 有字段需要更新
                    stream.save(update_fields=update_fields)
                    self.logger.info(f"更新视频流信息: width={width}, height={height}, fps={fps}")
                
        except Exception as e:
            self.logger.error(f"更新视频流信息失败: {e}")
    
    def start_save_thread(self):
        """动态启动保存线程"""
        if not self.ENABLE_SAVE or not self.video_stream.save_frames:
            self.logger.info("未启用保存帧")
            return
        
        if self.save_thread and self.save_thread.is_alive():
            self.logger.info("保存线程已在运行")
            return
            
        self.logger.info("启动保存线程")
        self.save_thread = threading.Thread(target=self.save_loop, name=f"save-{self.video_stream.id}")
        self.save_thread.start()
    
    def stop_save_thread(self):
        """动态停止保存线程"""
        if self.save_thread and self.save_thread.is_alive():
            # 通过设置 _stop_save_thread 标志停止保存线程
            self.logger.info("停止保存线程")
            self._stop_save_thread = True
            self.save_thread.join(timeout=2.0)
            if self.save_thread.is_alive():
                self.logger.warning("保存线程未能在2秒内正常结束")
            else:
                self.logger.info("保存线程已停止")
            self.save_thread = None
            self._stop_save_thread = False
        else:
            self.logger.info("保存线程未运行")


# 全局处理器管理
active_processors: dict[int, VideoStreamProcessor] = {}

# 全局清理线程
cleanup_thread = None
cleanup_running = False
cleanup_stop_event = threading.Event()


def get_processor(video_stream_id: int) -> Optional[VideoStreamProcessor]:
    """获取指定视频流的处理器"""
    return active_processors.get(video_stream_id)


def create_processor(video_stream) -> VideoStreamProcessor:
    """创建并启动视频流处理器"""
    logger.info(f"创建视频流处理器: {video_stream.id}")
    processor = VideoStreamProcessor(video_stream)
    active_processors[video_stream.id] = processor
    processor.start()
    return processor


def remove_processor(video_stream_id: int):
    """停止并移除视频流处理器"""
    logger.info(f"移除视频流处理器: {video_stream_id}")
    processor = active_processors.pop(video_stream_id, None)
    if processor:
        processor.stop()


def cleanup_loop():
    """清理线程：每分钟检查磁盘空间，必要时删除最旧的图片目录"""
    global cleanup_running, cleanup_stop_event
    
    while cleanup_running:
        try:
            # 检查磁盘剩余空间
            free_space_gb = get_free_space_gb(VideoStreamProcessor.SAVE_FRAMES_DIR)
            
            if free_space_gb < VideoStreamProcessor.SAFE_FREE_SPACE_GB:
                logger.warning(f"磁盘空间不足 {free_space_gb:.1f}GB < {VideoStreamProcessor.SAFE_FREE_SPACE_GB}GB，开始清理...")
                
                # 找到最旧的图片目录并删除
                oldest_dir = find_oldest_frame_directory()
                if oldest_dir:
                    try:
                        shutil.rmtree(oldest_dir)
                        logger.info(f"已删除最旧目录: {oldest_dir}")
                    except Exception as e:
                        logger.error(f"删除目录失败 {oldest_dir}: {e}")
                else:
                    logger.warning("未找到可删除的图片目录")
            else:
                logger.info(f"磁盘空间充足: {free_space_gb:.1f}GB")
            
            # 等待30秒后再次检查
            cleanup_stop_event.wait(timeout=30)
            
        except Exception as e:
            logger.error(f"清理线程错误: {e}")
            cleanup_stop_event.wait(timeout=30)

    logger.info("清理线程退出")

def get_free_space_gb(path: str) -> float:
    """获取指定路径的剩余磁盘空间（GB）"""
    try:
        statvfs = os.statvfs(path)
        free_bytes = statvfs.f_frsize * statvfs.f_bavail
        return free_bytes / (1024 ** 3)  # 转换为GB
    except Exception as e:
        logger.error(f"获取磁盘空间失败: {e}")
        return float('inf')  # 返回无限大，避免误删

def find_oldest_frame_directory() -> Optional[str]:
    """找到最旧的5分钟图片目录"""
    base_dir = VideoStreamProcessor.SAVE_FRAMES_DIR
    
    if not os.path.exists(base_dir):
        return None
    
    oldest_dir = None
    oldest_time = None
    
    try:
        # 遍历所有流目录
        for stream_dir in os.listdir(base_dir):
            stream_path = os.path.join(base_dir, stream_dir)
            if not os.path.isdir(stream_path) or not stream_dir.startswith('stream_'):
                continue
            
            # 遍历该流的所有时间目录
            for time_dir in os.listdir(stream_path):
                time_path = os.path.join(stream_path, time_dir)
                if not os.path.isdir(time_path):
                    continue
                
                # 获取目录的修改时间
                dir_mtime = os.path.getmtime(time_path)
                
                if oldest_time is None or dir_mtime < oldest_time:
                    oldest_time = dir_mtime
                    oldest_dir = time_path
    
    except Exception as e:
        logger.error(f"查找最旧目录时出错: {e}")
        return None
    
    return oldest_dir

def start_cleanup_thread():
    """启动清理线程"""
    global cleanup_thread, cleanup_running
    
    if cleanup_thread and cleanup_thread.is_alive():
        logger.info("清理线程已在运行")
        return
    
    cleanup_running = True
    cleanup_thread = threading.Thread(target=cleanup_loop, name="frame-cleanup")
    cleanup_thread.start()
    logger.info("清理线程已启动")

def stop_cleanup_thread():
    """停止清理线程"""
    global cleanup_thread, cleanup_running, cleanup_stop_event
    
    cleanup_running = False
    cleanup_stop_event.set()
    if cleanup_thread and cleanup_thread.is_alive():
        cleanup_thread.join(timeout=5.0)
        if cleanup_thread.is_alive():
            logger.warning("清理线程未能在5秒内正常结束")
        else:
            logger.info("清理线程已停止")

def shutdown_all_processors():
    """关闭所有活跃的视频流处理器"""
    logger.info(f"正在关闭 {len(active_processors)} 个视频流处理器...")
    
    # 停止清理线程
    stop_cleanup_thread()
    
    # 复制一份 keys，避免在迭代时修改字典
    processor_ids = list(active_processors.keys())
    
    for stream_id in processor_ids:
        try:
            remove_processor(stream_id)
            logger.info(f"已关闭视频流处理器: {stream_id}")
        except Exception as e:
            logger.error(f"关闭视频流处理器 {stream_id} 失败: {e}")
    
    logger.info("所有视频流处理器已关闭")
