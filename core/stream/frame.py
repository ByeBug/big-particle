"""
解码帧数据类
"""
import logging
from typing import Any
import cv2
import numpy as np

from .algorithm.status import InferStatus

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
        """
        self.ocv_image = ocv_image
        self.width = width
        self.height = height
        self.frame_number = frame_number
        self.timestamp = timestamp
        self.stream_id = stream_id
        
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
    