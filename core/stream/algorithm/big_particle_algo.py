"""
大颗粒检测算法
"""
import cv2
import logging
from datetime import datetime
import time
from concurrent.futures import Future

from django.utils import timezone

from .status import InferStatus
from .thread_pool import get_algo_thread_pool, get_io_thread_pool
from .model.model_manager import ModelManager
from ..frame import DecodedFrame
from .model.instance import Instance
from .model.paddle_detector import PaddleDetector
from ..logging_utils import StreamLoggerAdapter
from ..save_utils import RENDERED_DIR, save_image
from core.models import AlgoBigParticleRecord

logger = logging.getLogger(__name__)


class BigParticleAlgo:
    """大颗粒检测算法"""
    
    def __init__(self, stream_id: int, algo_config: dict = None):
        """
        初始化大颗粒算法实例
        
        Args:
            stream_id: 视频流ID
            algo_config: 算法配置参数，如阈值等
        """
        self.stream_id = stream_id
        self.name = algo_config['name']
        self.algo_config = algo_config or {}
        self.threshold = self.algo_config['threshold']
        self.size_threshold = sorted([threshold['size_level'] for threshold in self.algo_config['alarm_threshold']])[0]
        # 设置带 StreamID 的日志器
        self.logger = StreamLoggerAdapter(logger, {'stream_id': stream_id})
        
        # 获取模型
        self.detector: PaddleDetector = ModelManager.get_model(
            model_class=PaddleDetector,
            model_path=self.algo_config['model_path'],
            max_batch_size=self.algo_config['max_batch_size'],
        )

        self.instances: list[Instance] = []
        # 上一帧的实例，用于 IoU 去重
        self.prev_instances: list[Instance] = []
        # IoU 阈值，超过该阈值认为是同一颗粒
        self.iou_threshold: float = self.algo_config.get('iou_threshold', 0.8)

        self.logger.info(f"已初始化算法实例: {self.name}")
    
    def update_config(self, algo_config: dict):
        """
        更新算法配置
        """
        try:
            self.algo_config = algo_config
            self.threshold = self.algo_config['threshold']
            self.size_threshold = sorted([threshold['size_level'] for threshold in self.algo_config['alarm_threshold']])[0]
            self.iou_threshold = self.algo_config.get('iou_threshold', 0.8)
            self.logger.info(f"算法 {self.name} 已更新配置")
        except:
            self.logger.exception(f"算法 {self.name} 更新配置失败")
    
    def submit(self, frame: DecodedFrame) -> Future:
        """
        提交帧到全局线程池进行处理
        
        Args:
            frame: 待处理的解码帧
            
        Returns:
            Future: 异步任务对象
        """
        # 提交到全局线程池
        future = get_algo_thread_pool().submit(self.handle, frame)
        
        self.logger.debug(f"提交帧处理任务: frame={frame.frame_number}")
        
        return future
    
    def handle(self, frame: DecodedFrame):
        """
        处理单帧的具体实现
        
        Args:
            frame: 待处理的解码帧
        """
        try:
            algo_status = frame.algo_status[self.name]
            algo_running_info = frame.algo_running_info[self.name]
            
            if algo_status == InferStatus.NEED_INFER:
                # 推理：提交到模型队列并等待完成，推理失败直接返回，不进行后续处理
                algo_running_info['infer_start_time'] = time.time()
                if self.detector.submit_frame(frame):
                    # 等待模型推理完成（最多等待1秒）
                    if frame.model_events[self.detector.model_name].wait(timeout=1.0):
                        self.logger.debug(f"推理完成: frame={frame.frame_number}")
                    else:
                        self.logger.warning(f"推理超时: frame={frame.frame_number}")
                        return
                else:
                    self.logger.warning(f"提交帧失败: frame={frame.frame_number}")
                    return
                algo_running_info['infer_end_time'] = time.time()
                
                # 模型推理完成，设置最新的推理结果，进行业务逻辑处理等，设置帧的算法结果
                instances: list[Instance] = frame.model_results[self.detector.model_name]   # 未过滤的模型结果
                self.instances = []
                for instance in instances:
                    if instance.score < self.threshold:
                        continue
                    # TODO 计算粒径，单位为毫米
                    instance.size = round(min(instance.right - instance.left, instance.bottom - instance.top) * 0.4)
                    # 忽略小于尺寸阈值的颗粒
                    if instance.size < self.size_threshold:
                        continue
                    # TODO 与黑名单做 IoU 去重
                    # 与上一帧做 IoU 去重，超过阈值则认为是同一颗粒，避免皮带未运行时重复记录同一颗粒 TODO 会跳帧重复记录
                    if self._is_duplicate_with_prev(instance):
                        continue
                    instance.id = len(self.instances)
                    self.instances.append(instance)
                
                self.prev_instances = self.instances
                frame.algo_results[self.name] = self.instances
            
            # 推理结果处理完立刻渲染，先于其他业务逻辑，以便在编码前完成渲染
            # 有检测结果才获取画布
            if self.instances:
                algo_running_info['render_start_time'] = time.time()
                canvas = frame.canvas
                self._render(canvas, self.instances)
                algo_running_info['render_end_time'] = time.time()

            if algo_status == InferStatus.NEED_INFER:
                # 对于推理的帧执行后续的业务逻辑，如保存记录等
                if self.instances:
                    # 异步保存大颗粒记录，不阻塞算法线程
                    get_io_thread_pool().submit(self._save_record, frame)

            # 设置算法完成状态
            frame.algo_status[self.name] = InferStatus.DONE
            
            self.logger.debug(f"算法处理完成: frame={frame.frame_number}, status={algo_status}")

        except Exception as e:
            self.logger.error(f"算法处理失败: frame={frame.frame_number}, error={e}")
            # 设置失败状态
            frame.algo_status[self.name] = InferStatus.FAILED
        finally:
            # 无论成功还是失败，都要 count down
            frame.algo_latch.count_down()

    def _render(self, image, instances: list[Instance]):
        """
        渲染帧
        """
        # 无渲染对象直接返回
        if not instances:
            return
        
        for instance in instances:
            # 提取边界框坐标 (x1, y1, x2, y2)
            x1, y1, x2, y2 = instance.left, instance.top, instance.right, instance.bottom
            # 绘制红色矩形框
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 2)

    def _is_duplicate_with_prev(self, curr: Instance) -> bool:
        """与上一帧做 IoU 比较，若大于阈值则认为是同一颗粒"""
        if not self.prev_instances:
            return False
        for prev in self.prev_instances:
            if self._calc_iou(curr, prev) >= self.iou_threshold:
                return True
        return False

    def _calc_iou(self, a: Instance, b: Instance) -> float:
        """计算两个检测框的 IoU"""
        ax1, ay1, ax2, ay2 = a.left, a.top, a.right, a.bottom
        bx1, by1, bx2, by2 = b.left, b.top, b.right, b.bottom

        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)

        inter_w = max(0, inter_x2 - inter_x1)
        inter_h = max(0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h

        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
        union_area = area_a + area_b - inter_area
        if union_area <= 0:
            return 0.0
        return inter_area / union_area

    def _save_record(self, frame: DecodedFrame):
        """
        保存记录
        
        Args:
            frame: 检测帧
        """
        try:
            instances = frame.algo_results[self.name]
            if not instances:
                return
                
            # 计算粒径范围
            sizes = [instance.size for instance in instances]
                
            min_size = min(sizes)
            max_size = max(sizes)
            
            # 获取原图ID（多算法共享）TODO 不共享
            original_image_id = frame.get_original_image_id()
            
            rendered_image_id = None
            if frame.has_canvas():  # TODO 多算法时，切换为对原图再次渲染
                file_name = RENDERED_DIR / f"{self.name}/stream_{frame.stream_id}_{frame.timestamp}.jpg"
                try:
                    rendered_image_id = save_image(frame.canvas, str(file_name))
                except Exception as e:
                    self.logger.error(f"保存渲染图失败: {e}")

            # 创建记录
            detected_at = datetime.fromtimestamp(frame.algo_running_info[self.name]['infer_start_time'],
                                                 tz=timezone.get_current_timezone())
            result = [{**instance.to_dict(), 'size': instance.size} for instance in instances]
            record = AlgoBigParticleRecord.objects.create(
                stream_id=frame.stream_id,
                stream_name=frame.stream_name,
                min_size=min_size,
                max_size=max_size,
                detected_at=detected_at,
                result=result,
                original_image_id=original_image_id,
                rendered_image_id=rendered_image_id
            )
            
            self.logger.debug(f"保存大颗粒记录成功: record_id={record.id}")
            
        except Exception as e:
            self.logger.exception(f"保存大颗粒记录失败: error={e}")
