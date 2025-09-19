"""
大颗粒检测算法
"""
import cv2
import logging
from datetime import datetime
import time
import threading
from concurrent.futures import Future

from django.utils import timezone

from .status import InferStatus
from .thread_pool import get_algo_thread_pool, get_io_thread_pool
from .model.model_manager import ModelManager
from ..frame import DecodedFrame
from .model.instance import Instance
from .model.paddle_detector import PaddleDetector
from ..logging_utils import StreamLoggerAdapter
from ..save_utils import ORIGINAL_DIR, RENDERED_DIR, ALARM_DIR, save_image
from core.models import AlgoRecord, AlgoBigParticleDetail, Alarm

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
        self.alarm_threshold_map = {}
        for alarm_threshold in self.algo_config['alarm_threshold']:
            self.alarm_threshold_map[alarm_threshold['size_level']] = alarm_threshold
        self.size_levels = sorted([size_level for size_level in self.alarm_threshold_map.keys()])
        self.size_threshold = self.size_levels[0]
        # 设置带 StreamID 的日志器
        self.logger = StreamLoggerAdapter(logger, {'stream_id': stream_id})
        
        # 获取模型
        self.detector: PaddleDetector = ModelManager.get_model(
            model_class=PaddleDetector,
            model_path=self.algo_config['model_path'],
            max_batch_size=self.algo_config['max_batch_size'],
        )

        self.instances: list[Instance] = []
        # 上一帧的所有实例（包括有效的和被抑制的），用于 IoU 去重
        self.prev_all_instances: list[Instance] = []
        # IoU 阈值，超过该阈值认为是同一颗粒
        self.iou_threshold: float = self.algo_config.get('iou_threshold', 0.8)

        # 每小时不同粒径颗粒数量统计，{20250910_01: {size: count}}
        self.hour_size_count_map: dict[str, dict[int, int]] = {}
        self.prev_hour_str = ''
        self.hour_size_lock = threading.Lock()

        # 每小时不同粒径等级的告警
        self.hour_size_level_alarm_map: dict[str, dict[str, dict]] = {}
        self.prev_calc_alarm_ts = -1

        self.logger.info(f"已初始化算法实例: {self.name}")
    
    def update_config(self, algo_config: dict):
        """
        更新算法配置
        """
        try:
            self.algo_config = algo_config
            self.threshold = self.algo_config['threshold']
            self.alarm_threshold_map = {}
            for alarm_threshold in self.algo_config['alarm_threshold']:
                self.alarm_threshold_map[alarm_threshold['size_level']] = alarm_threshold
            self.size_levels = sorted([size_level for size_level in self.alarm_threshold_map.keys()])
            self.size_threshold = self.size_levels[0]
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
                current_all_instances = []  # 当前帧所有检测到的实例
                current_suppressed_instances = []  # 当前帧被抑制的实例
                
                for instance in instances:
                    # 先进行较为宽松的过滤，避免在 threshold 上下波动，导致抑制不稳
                    if instance.score < self.threshold - 0.1:
                        continue
                    # 计算粒径，单位为毫米
                    instance.size = round(min(instance.right - instance.left, instance.bottom - instance.top) * 0.62)
                    if instance.size < self.size_threshold - 5:
                        continue
                    current_all_instances.append(instance)

                    # 再进行业务上的过滤
                    if instance.score < self.threshold:
                        continue
                    # 忽略小于尺寸阈值的颗粒
                    if instance.size < self.size_threshold:
                        continue
                    
                    # TODO 与黑名单做 IoU 去重
                    
                    # 与上一帧所有实例做 IoU 去重，超过阈值则认为是同一颗粒，避免皮带未运行时重复记录同一颗粒
                    if self._is_duplicate_with_prev(instance):
                        current_suppressed_instances.append(instance)
                        continue
                    
                    instance.id = len(self.instances)
                    self.instances.append(instance)
                self.logger.debug(f"当前帧实例总数：{len(current_all_instances)}，被抑制数：{len(current_suppressed_instances)}")
                
                # 更新上一帧的所有实例（包括有效的和被抑制的）
                self.prev_all_instances = current_all_instances
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
        """与上一帧所有实例做 IoU 比较，若大于阈值则认为是同一颗粒"""
        if not self.prev_all_instances:
            return False
        for prev in self.prev_all_instances:
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
            
            # 获取原图ID（多算法不共享，避免删除算法记录时影响其他算法）
            original_image_id = None
            file_path = ORIGINAL_DIR / f"{self.name}/stream_{frame.stream_id}_{frame.timestamp}.png"
            try:
                original_image_id = save_image(frame.ocv_image, file_path)
            except Exception as e:
                self.logger.error(f"保存原始图失败: {e}")
            
            rendered_image_id = None
            if frame.has_canvas():  # TODO 多算法时，切换为对原图再次渲染
                file_path = RENDERED_DIR / f"{self.name}/stream_{frame.stream_id}_{frame.timestamp}.jpg"
                try:
                    rendered_image_id = save_image(frame.canvas, file_path)
                except Exception as e:
                    self.logger.error(f"保存渲染图失败: {e}")

            # 创建记录
            detected_at = datetime.fromtimestamp(frame.algo_running_info[self.name]['infer_start_time'],
                                                 tz=timezone.get_current_timezone())
            result = [{**instance.to_dict(), 'size': instance.size} for instance in instances]
            record = AlgoRecord.objects.create(
                stream_id=frame.stream_id,
                stream_name=frame.stream_name,
                algo_name=self.name,
                detected_at=detected_at,
                result=result,
                original_image_id=original_image_id,
                rendered_image_id=rendered_image_id
            )
            
            # 保存实例详情记录
            instance_records = []
            for instance in result:
                instance_record = AlgoBigParticleDetail(
                    stream_id=frame.stream_id,
                    stream_name=frame.stream_name,
                    size=instance['size'],
                    record_id=record.id,
                    instance=instance,
                    detected_at=detected_at
                )
                instance_records.append(instance_record)
            
            # 批量创建实例记录
            AlgoBigParticleDetail.objects.bulk_create(instance_records)
            
            self.logger.debug(f"保存大颗粒记录成功: record_id={record.id}, 实例数量：{len(instance_records)}")
            
        except Exception as e:
            self.logger.exception(f"保存大颗粒记录失败: error={e}")
        
        # 告警逻辑
        with self.hour_size_lock:
            now = datetime.now()
            current_hour_str = now.strftime('%Y%m%d_%H')
            # 进入新的小时后，清理上一小时的统计
            if current_hour_str != self.prev_hour_str:
                if self.prev_hour_str in self.hour_size_count_map:
                    del self.hour_size_count_map[self.prev_hour_str]
                if self.prev_hour_str in self.hour_size_level_alarm_map:
                    del self.hour_size_level_alarm_map[self.prev_hour_str]
                self.hour_size_count_map[current_hour_str] = {}
                self.hour_size_level_alarm_map[current_hour_str] = {}
                self.prev_hour_str = current_hour_str
            
            # 不同粒径数量统计
            current_hour_size_count_map = self.hour_size_count_map[current_hour_str]
            for instance in instances:
                size = instance.size
                current_hour_size_count_map[size] = current_hour_size_count_map.get(size, 0) + 1
            
            # 是否需要计算告警，距上次 5s 后再计算
            need_calc_alarm = False
            if now.timestamp - self.prev_calc_alarm_ts >= 5:
                self.prev_calc_alarm_ts = now.timestamp
                need_calc_alarm = True
        
        if need_calc_alarm:
            current_hour_size_level_alarm_map = self.hour_size_level_alarm_map[current_hour_str]
            # 当前小时内，大于粒径阈值的颗粒总数，用于计算各等级的百分比
            total_count = 0
            for size, count in current_hour_size_count_map.items():
                if size >= self.size_threshold:
                    total_count += count
            
            for i, size_level in enumerate(self.size_levels):
                included_min_size = size_level
                excluded_max_size = None if i == len(self.size_levels) - 1 else self.size_levels[i + 1]
                size_level_str = f'>={included_min_size}' if i == len(self.size_levels) - 1 else f'{included_min_size}-{excluded_max_size}'
                if size_level_str not in current_hour_size_level_alarm_map:
                    current_hour_size_level_alarm_map[size_level_str] = {
                        'error_count': self.alarm_threshold_map[size_level].get('error_count', None),
                        'error_percentage': self.alarm_threshold_map[size_level].get('error_percentage', None),
                        'count': 0,
                        'percentage': 0,
                        'alarmed': False,
                    }
                size_level_alarm = current_hour_size_level_alarm_map[size_level_str]

                # 若该等级已告警过，则跳过
                if size_level_alarm['alarmed']:
                    continue

                # 重置该等级的计数
                size_level_alarm['count'] = 0

                # 计算该等级颗粒数量和百分比
                for size, count in current_hour_size_count_map.items():
                    if size < included_min_size:
                        continue
                    elif excluded_max_size is not None and size >= excluded_max_size:
                        continue
                    else:
                        size_level_alarm['count'] += count
                size_level_alarm['percentage'] = round(size_level_alarm['count'] / total_count * 100, 2) if total_count > 0 else 0.0
                
                # 判断是否告警
                generate_alarm = False
                if size_level_alarm['error_count'] is not None and size_level_alarm['count'] >= size_level_alarm['error_count']:
                    generate_alarm = True
                    alarm_data = {
                        'size_level': size_level_str,
                        'error_count': size_level_alarm['error_count'],
                        'count': size_level_alarm['count'],
                    }
                # 百分比告警会覆盖数量告警
                if size_level_alarm['error_percentage'] is not None and size_level_alarm['percentage'] >= size_level_alarm['error_percentage']:
                    generate_alarm = True
                    alarm_data = {
                        'size_level': size_level_str,
                        'error_percentage': size_level_alarm['error_percentage'],
                        'percentage': size_level_alarm['percentage'],
                    }
                
                if generate_alarm:
                    try:
                        alarm_image_id = None
                        if frame.has_canvas():  # TODO 多算法时，切换为对原图再次渲染
                            file_path = ALARM_DIR / f"{self.name}/stream_{frame.stream_id}_{frame.timestamp}.jpg"
                            try:
                                alarm_image_id = save_image(frame.canvas, file_path)
                            except Exception as e:
                                self.logger.error(f"保存告警图失败: {e}")
                        
                        alarm_original_image_id = None
                        file_path = ALARM_DIR / f"{self.name}/stream_{frame.stream_id}_{frame.timestamp}.png"
                        try:
                            alarm_original_image_id = save_image(frame.ocv_image, file_path)
                        except Exception as e:
                            self.logger.error(f"保存告警原图失败: {e}")
                        
                        Alarm.objects.create(
                            alarm_type='big_particle',
                            stream_id=frame.stream_id,
                            stream_name=frame.stream_name,
                            data=alarm_data,
                            alarm_time=timezone.now(),
                            record_id=record.id,
                            alarm_image_id=alarm_image_id,
                            original_image_id=alarm_original_image_id,
                        )

                        size_level_alarm['alarmed'] = True
                        self.logger.info(f"生成告警: {alarm_data}")
                    except Exception as e:
                        self.logger.exception(f"生成告警失败: {e}")
