"""
大颗粒检测算法
"""
import logging
import time
from concurrent.futures import Future

from .status import InferStatus
from .thread_pool import get_global_thread_pool
from ..frame import DecodedFrame

logger = logging.getLogger(__name__)


class BigParticleAlgo:
    """大颗粒检测算法"""
    
    def __init__(self, stream_id: int, name: str, algorithm_config: dict = None):
        """
        初始化大颗粒算法实例
        
        Args:
            stream_id: 视频流ID
            algorithm_config: 算法配置参数，如阈值等
        """
        self.stream_id = stream_id
        self.name = name
        self.algorithm_config = algorithm_config or {}
        self.logger = logging.getLogger(f"{__name__}.{stream_id}")
        
        # TODO 初始化模型
        self.logger.info(f"已初始化算法实例: stream_id={stream_id}, name={name}")
    
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
            
        Returns:
            处理结果（具体格式待定）
        """
        try:
            # TODO: 实现具体的大颗粒检测逻辑
            # 目前只是模拟处理时间
            if frame.algo_status[self.name] == InferStatus.NEED_INFER:
                time.sleep(0.05)
            elif frame.algo_status[self.name] == InferStatus.NEED_RENDER:
                time.sleep(0.01)
            
            frame.algo_status[self.name] = InferStatus.DONE
            frame.algo_results[self.name] = []
            
            self.logger.debug(f"帧处理完成: frame={frame.frame_number}")
            
        except Exception as e:
            self.logger.error(f"帧处理失败: frame={frame.frame_number}, error={e}")
            raise  # 重新抛出异常，让调用者处理
