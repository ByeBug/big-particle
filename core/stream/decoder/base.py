"""
视频解码器基类
"""

import time
from abc import ABC, abstractmethod
from collections import deque
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..frame import DecodedFrame
import threading


class BaseDecoder(ABC):
    """视频解码器基类
    
    为不同类型的视频源提供统一的解码接口。
    支持的视频源类型：
    - MVS 相机
    - 视频文件
    - 图像目录
    """
    
    def __init__(self, video_stream, fps: Optional[int] = None):
        """
        初始化解码器
        
        Args:
            video_stream: VideoStream 模型实例
            fps: 目标帧率，如果为 None 则使用 video_stream.fps
        """
        self.video_stream = video_stream
        self.fps = fps or video_stream.fps or 30
        self.width = video_stream.width
        self.height = video_stream.height
        
        # 帧率控制
        self._target_interval = 1.0 / self.fps
        
        # 状态管理
        self._is_opened = False
        self._is_running = False
        self._lock = threading.Lock()
        
        # 统计信息
        self._frame_count = 0
        self._start_time = None
        self._last_frame_time = None
        
        # 实时帧率计算（5秒窗口）
        self._fps_window_size = 5.0  # 5秒窗口
        self._frame_timestamps = deque()  # 存储帧时间戳
    
    @abstractmethod
    def open(self) -> bool:
        """
        打开视频源
        
        Returns:
            bool: 是否成功打开
        """
        pass
    
    @abstractmethod
    def close(self):
        """
        关闭视频源
        """
        pass
    
    @abstractmethod
    def read_frame(self) -> Optional["DecodedFrame"]:
        """
        读取一帧数据
        
        Returns:
            Optional[DecodedFrame]: 解码帧对象，失败返回 None
        """
        pass
    
    @abstractmethod
    def is_opened(self) -> bool:
        """
        检查视频源是否已打开
        
        Returns:
            bool: 是否已打开
        """
        pass
    
    def get_frame_with_timing(self) -> Optional["DecodedFrame"]:
        """
        按照目标帧率读取帧数据，自动控制时间间隔
        
        Returns:
            Optional[DecodedFrame]: 解码帧对象，失败返回 None
        """
        if not self.is_opened():
            return None
        
        current_time = time.time()
        
        # 除第一帧外，等待时间间隔
        if self._last_frame_time is not None:
            elapsed = current_time - self._last_frame_time
            sleep_time = self._target_interval - elapsed
            
            if sleep_time > 0.001:  # 只有超过1ms才睡眠
                time.sleep(sleep_time)
                current_time = time.time()
        
        frame = self.read_frame()
        
        if frame is not None:
            with self._lock:
                self._frame_count += 1
                self._last_frame_time = current_time
                if self._start_time is None:
                    self._start_time = current_time
                
                # 记录帧时间戳用于实时帧率计算
                self._frame_timestamps.append(current_time)
                
                # 清理超过窗口时间的旧时间戳（从左侧移除）
                cutoff_time = current_time - self._fps_window_size
                while self._frame_timestamps and self._frame_timestamps[0] < cutoff_time:
                    self._frame_timestamps.popleft()
        
        return frame
    
    def get_actual_fps(self) -> float:
        """
        获取实际帧率（基于最近5秒的数据）
        
        Returns:
            float: 实际帧率
        """
        with self._lock:
            # 直接基于现有时间戳计算帧率（已经维护了5秒窗口）
            if len(self._frame_timestamps) < 2:
                return 0.0
            
            # 计算时间窗口内的帧率
            time_span = self._frame_timestamps[-1] - self._frame_timestamps[0]
            if time_span <= 0:
                return 0.0
            
            # 帧数 = 时间戳数量 - 1（因为第一帧不算间隔）
            frame_count = len(self._frame_timestamps) - 1
            return frame_count / time_span
    
    def get_frame_count(self) -> int:
        """
        获取已读取的帧数
        
        Returns:
            int: 帧数
        """
        with self._lock:
            return self._frame_count
    
    def reset_stats(self):
        """
        重置统计信息
        """
        with self._lock:
            self._frame_count = 0
            self._start_time = None
            self._last_frame_time = None
            self._frame_timestamps.clear()
    
    def get_stream_info(self) -> Dict[str, Any]:
        """
        获取视频流信息
        
        Returns:
            Dict[str, Any]: 视频流信息字典
        """
        return {
            'type': self.video_stream.type,
            'ip': self.video_stream.ip,
            'address': self.video_stream.address,
            'width': self.width,
            'height': self.height,
            'target_fps': self.fps,
            'actual_fps': self.get_actual_fps(),
            'frame_count': self.get_frame_count(),
            'is_opened': self.is_opened(),
        }
    
    def __enter__(self):
        """
        上下文管理器支持
        """
        if self.open():
            return self
        raise RuntimeError(f"无法打开视频源: {self.get_stream_info()}")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        上下文管理器支持
        """
        self.close()
    
    def __str__(self):
        return f"{self.__class__.__name__}({self.video_stream.get_type_display()}: {self.video_stream.ip or self.video_stream.address})"
    
    def __repr__(self):
        return f"{self.__class__.__name__}(video_stream={self.video_stream}, fps={self.fps})"