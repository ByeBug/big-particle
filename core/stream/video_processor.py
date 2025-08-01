import time
import queue
import threading
from typing import Optional

from .delayed_queue import DelayedQueue


class VideoStreamProcessor:
    """视频流处理器：包含解码、推理、编码三个线程"""
    # TODO 流的运行状态、宽高、实际 fps 更新到数据库
    
    ENCODE_DELAY_SEC = 0.5  # 编码延迟时间（秒）
    
    def __init__(self, video_stream):
        self.video_stream = video_stream
        self.fps = video_stream.fps or 30
        
        # 队列设置
        self.infer_queue = queue.Queue(maxsize=self.fps)
        # 编码队列大小 = fps * (延迟时间 + 缓冲时间)
        encode_queue_size = int(self.fps * (self.ENCODE_DELAY_SEC + 1))
        self.encode_queue = DelayedQueue(delay_seconds=self.ENCODE_DELAY_SEC, maxsize=encode_queue_size)
        
        # 线程
        self.decode_thread = None
        self.infer_thread = None
        self.encode_thread = None
        
        # 控制标志
        self.running = False
    
    def start(self):
        """启动所有处理线程"""
        if self.running:
            return
        
        self.running = True
        
        self.decode_thread = threading.Thread(target=self.decode_loop, name=f"decode-{self.video_stream.id}")
        self.infer_thread = threading.Thread(target=self.infer_loop, name=f"infer-{self.video_stream.id}")
        self.encode_thread = threading.Thread(target=self.encode_loop, name=f"encode-{self.video_stream.id}")
        
        self.decode_thread.start()
        self.infer_thread.start()
        self.encode_thread.start()
    
    def stop(self):
        """停止所有处理线程"""
        self.running = False
        
        # 等待所有线程正常结束
        threads = [self.decode_thread, self.infer_thread, self.encode_thread]
        for thread in threads:
            if thread and thread.is_alive():
                thread.join(timeout=5.0)  # 最多等待5秒
                if thread.is_alive():
                    print(f"警告: 线程 {thread.name} 未能在5秒内正常结束")
    
    def decode_loop(self):
        """解码线程：读取视频帧并分发到推理和编码队列"""
        while self.running:
            try:
                # TODO: 实现实际的解码逻辑
                frame = self.decode_frame()
                if frame is None:
                    time.sleep(0.01)
                    continue
                
                # 尝试加入推理队列
                try:
                    self.infer_queue.put_nowait(frame)
                except queue.Full:
                    pass  # 推理队列满，丢弃帧
                
                # 尝试加入编码队列（延时500ms出队）
                try:
                    self.encode_queue.put_nowait(frame)
                except queue.Full:
                    pass  # 编码队列满，丢弃帧
                
            except Exception as e:
                print(f"解码线程错误: {e}")
                time.sleep(0.1)
    
    def infer_loop(self):
        """推理线程：处理推理队列中的帧"""
        while self.running:
            try:
                frame = self.infer_queue.get(timeout=1.0)
                # TODO: 实现实际的推理逻辑
                self.process_inference(frame)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"推理线程错误: {e}")
    
    def encode_loop(self):
        """编码线程：处理编码队列中的帧（自动延时500ms）"""
        while self.running:
            try:
                frame = self.encode_queue.get()
                # TODO: 实现实际的编码逻辑
                self.encode_frame(frame)
            except Exception as e:
                print(f"编码线程错误: {e}")
    
    def decode_frame(self):
        """解码一帧数据"""
        # TODO: 根据 video_stream 的类型和地址实现具体解码逻辑
        # - MVS 相机：从相机获取图像
        # - VIDEO_FILE：从视频文件读取帧
        # - IMAGE_DIR：从图像目录读取图片
        time.sleep(1.0 / self.fps)  # 模拟帧率
        return f"frame_{time.time()}"
    
    def process_inference(self, frame):
        """处理推理"""
        # TODO: 实现大颗粒检测推理逻辑
        print(f"推理处理: {frame}")
        time.sleep(0.1)  # 模拟推理时间
    
    def encode_frame(self, frame):
        """编码一帧数据"""
        # TODO: 实现编码逻辑，输出编码后的视频流
        print(f"编码处理: {frame}")
        time.sleep(0.05)  # 模拟编码时间


# 全局处理器管理
active_processors = {}


def get_processor(video_stream_id: int) -> Optional[VideoStreamProcessor]:
    """获取指定视频流的处理器"""
    return active_processors.get(video_stream_id)


def create_processor(video_stream) -> VideoStreamProcessor:
    """创建并启动视频流处理器"""
    processor = VideoStreamProcessor(video_stream)
    active_processors[video_stream.id] = processor
    processor.start()
    return processor


def remove_processor(video_stream_id: int):
    """停止并移除视频流处理器"""
    processor = active_processors.pop(video_stream_id, None)
    if processor:
        processor.stop()


def shutdown_all_processors():
    """关闭所有活跃的视频流处理器"""
    print(f"正在关闭 {len(active_processors)} 个视频流处理器...")
    
    # 复制一份 keys，避免在迭代时修改字典
    processor_ids = list(active_processors.keys())
    
    for stream_id in processor_ids:
        try:
            remove_processor(stream_id)
            print(f"已关闭视频流处理器: {stream_id}")
        except Exception as e:
            print(f"关闭视频流处理器 {stream_id} 失败: {e}")
    
    print("所有视频流处理器已关闭")