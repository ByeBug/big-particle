"""
大颗粒检测算法
"""
import logging
import time
from concurrent.futures import Future

from .status import InferStatus
from .thread_pool import get_global_thread_pool
from .model.model_manager import ModelManager
from ..frame import DecodedFrame
from .model.paddle_detector import PaddleDetector
from ..logging_utils import StreamLoggerAdapter

logger = logging.getLogger(__name__)


class BigParticleAlgo:
    """大颗粒检测算法"""
    
    def __init__(self, stream_id: int, algo_config: dict = None):
        """
        初始化大颗粒算法实例
        
        Args:
            stream_id: 视频流ID
            algorithm_config: 算法配置参数，如阈值等
        """
        self.stream_id = stream_id
        self.name = algo_config['name']
        self.algo_config = algo_config or {}
        # 设置带 StreamID 的日志器
        self.logger = StreamLoggerAdapter(logger, {'stream_id': stream_id})
        
        # 获取模型
        self.detector: PaddleDetector = ModelManager.get_model(
            model_class=PaddleDetector,
            model_path=self.algo_config['model_path'],
            batch_size=self.algo_config['batch_size']
        )

        self.logger.info(f"已初始化算法实例: {self.name}")
    
    def submit(self, frame: DecodedFrame) -> Future:
        """
        提交帧到全局线程池进行处理
        
        Args:
            frame: 待处理的解码帧
            
        Returns:
            Future: 异步任务对象
        """
        # 提交到全局线程池
        future = get_global_thread_pool().submit(self.handle, frame)
        
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
            
            if algo_status == InferStatus.NEED_INFER:
                # 推理：提交到模型队列并等待完成，推理失败直接返回，不进行后续处理
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
                
                # TODO 模型推理完成，设置最新的推理结果，进行业务逻辑处理等，设置帧的算法结果
                frame.algo_results[self.name] = []
            
            # TODO 渲染

            if algo_status == InferStatus.NEED_INFER:
                # TODO 对于推理的帧执行后续的业务逻辑，如保存记录等
                pass

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
