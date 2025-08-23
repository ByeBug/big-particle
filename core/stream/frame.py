"""
解码帧数据类
"""
import logging
import threading
from typing import Any, Optional, DefaultDict
from collections import defaultdict
import cv2
import numpy as np

from .algorithm.status import InferStatus
from .count_down_latch import CountDownLatch

logger = logging.getLogger(__name__)


class DecodedFrame:
    """解码出的帧
    
    封装从不同视频源解码出的图像数据，提供统一的接口
    """
    
    def __init__(
        self,
        ocv_image: np.ndarray,
        width: int,
        height: int,
        frame_number: int,
        timestamp: int,
        stream_id: int,
        stream_name: str,
    ):
        """
        初始化解码帧
        
        Args:
            ocv_image: OpenCV 格式的图像数据 (numpy.ndarray)
            width: 图像宽度
            height: 图像高度
            frame_number: 帧号
            timestamp: 毫秒时间戳
            stream_id: 视频流ID（对应 VideoStream 模型的 ID）
            stream_name: 视频流名称
        """
        self.ocv_image = ocv_image
        self.width = width
        self.height = height
        self.frame_number = frame_number
        self.timestamp = timestamp
        self.stream_id = stream_id
        self.stream_name = stream_name

        # 自动计算通道数
        if len(ocv_image.shape) == 2:
            # 灰度图：(height, width)
            self.channels = 1
        elif len(ocv_image.shape) == 3:
            # 彩色图：(height, width, channels)
            self.channels = ocv_image.shape[2]
        else:
            raise ValueError(f"不支持的图像维度: {ocv_image.shape}")
        
        # 算法状态字典 {algo_name: InferStatus}
        self.algo_status: dict[str, InferStatus] = {}
        # 算法结果字典 {algo_name: Any}
        self.algo_results: dict[str, Any] = {}
        # 算法运行信息字典 {algo_name: dict}
        self.algo_running_info: DefaultDict[str, dict] = defaultdict(dict)
        # 模型完成事件字典 {model_name, threading.Event}
        self.model_events: dict[str, threading.Event] = {}
        # 模型结果字典 {model_name, Any}
        self.model_results: dict[str, Any] = {}
        
        # CountDownLatch: 等待所有算法完成
        self.algo_latch: Optional[CountDownLatch] = None
        
        # 画布相关属性
        self._canvas: Optional[np.ndarray] = None
        self._canvas_lock = threading.Lock()
        
        # 原图保存相关
        self._original_image_id: Optional[int] = None
        self._original_image_lock = threading.Lock()
    
    @property
    def shape(self) -> tuple:
        """获取图像形状 (height, width, channels)"""
        return self.ocv_image.shape
    
    @property
    def dtype(self) -> np.dtype:
        """获取图像数据类型"""
        return self.ocv_image.dtype
    
    @property
    def size(self) -> int:
        """获取图像像素总数"""
        return self.ocv_image.size
    
    @property
    def is_color(self) -> bool:
        """判断是否为彩色图像"""
        return self.channels > 1
    
    @property
    def is_gray(self) -> bool:
        """判断是否为灰度图像"""
        return self.channels == 1
    
    @property
    def canvas(self) -> np.ndarray:
        """
        获取用于绘制推理结果的画布
        
        画布是 ocv_image 的深度复制，供各种算法在其上绘制推理结果。
        使用线程安全的懒加载机制，多个算法线程可以安全地访问。
        
        Returns:
            np.ndarray: 用于绘制的画布副本
        """
        with self._canvas_lock:
            if self._canvas is None:
                if self.is_gray:
                    self._canvas = cv2.cvtColor(self.ocv_image, cv2.COLOR_GRAY2BGR)
                else:
                    self._canvas = self.ocv_image.copy()
            return self._canvas
    
    def has_canvas(self) -> bool:
        """
        判断是否已创建画布
        
        用于渲染线程判断是否有算法在画布上绘制过内容，
        如果有则使用画布进行渲染，否则使用原图。
        
        Returns:
            bool: 是否已创建画布
        """
        with self._canvas_lock:
            return self._canvas is not None
    
    def get_original_image_id(self) -> Optional[int]:
        """
        获取原图ID（线程安全，避免重复保存）
        
        Returns:
            int: 原图OSS对象ID
        """
        with self._original_image_lock:
            if self._original_image_id is None:
                from .save_utils import save_original_frame
                self._original_image_id = save_original_frame(self)
            return self._original_image_id
    
    def save(self, file_path: str) -> bool:
        """
        保存图像到文件
        
        Args:
            file_path: 保存路径
            
        Returns:
            bool: 是否保存成功
        """
        try:
            return cv2.imwrite(file_path, self.ocv_image)
        except Exception as e:
            logger.error(f"保存图像失败: {e}")
            return False
    
    def __str__(self) -> str:
        return (f"DecodedFrame({self.width}x{self.height}x{self.channels}, "
                f"frame={self.frame_number}, stream_id={self.stream_id})")
    
    def __repr__(self) -> str:
        return (f"DecodedFrame(width={self.width}, height={self.height}, channels={self.channels}, "
                f"frame_number={self.frame_number}, timestamp={self.timestamp}, "
                f"stream_id={self.stream_id}, dtype={self.dtype})")
    