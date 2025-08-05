"""
视频文件解码器
"""

import os
import time
import cv2
from typing import Optional

from .base import BaseDecoder
from ..frame import DecodedFrame


class VideoFileDecoder(BaseDecoder):
    """视频文件解码器
    
    用于从视频文件读取帧数据
    TODO 视频应尊重文件的帧率，而不是设置的采集帧率
    """
    
    def __init__(self, video_stream):
        super().__init__(video_stream)
        self._cap = None
    
    def open(self) -> bool:
        """
        打开视频文件
        
        Returns:
            bool: 是否成功打开
        """
        try:
            if self._is_opened:
                return True
            
            file_path = self.video_stream.address
            if not file_path:
                print("视频文件地址不能为空")
                return False
            
            if not os.path.exists(file_path):
                print(f"视频文件不存在: {file_path}")
                return False
            
            # 打开视频文件
            self._cap = cv2.VideoCapture(file_path)
            
            if not self._cap.isOpened():
                print(f"无法打开视频文件: {file_path}")
                return False
            
            # 获取视频信息
            video_fps = int(round(self._cap.get(cv2.CAP_PROP_FPS)))
            video_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            video_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # 更新实例属性
            self.width = video_width
            self.height = video_height
            self.fps = video_fps
            
            # 更新了 fps 要重新设置 interval
            self._target_interval = 1.0 / self.fps if self.fps else 0.1
            
            self._is_opened = True
            self.reset_stats()
            
            print(f"成功打开视频文件: {file_path}")
            print(f"视频信息: {video_width}x{video_height}, {video_fps}fps, {frame_count}帧")
            
            return True
            
        except Exception as e:
            print(f"打开视频文件失败: {e}")
            return False
    
    def close(self):
        """
        关闭视频文件
        """
        try:
            if self._cap:
                self._cap.release()
                print(f"成功关闭视频文件: {self.video_stream.address}")
            
            self._cap = None
            self._is_opened = False
            
        except Exception as e:
            print(f"关闭视频文件失败: {e}")
    
    def read_frame(self) -> Optional[DecodedFrame]:
        """
        从视频文件读取一帧
        
        Returns:
            Optional[DecodedFrame]: 解码帧对象，失败返回 None
        """
        if not self._is_opened or not self._cap:
            return None
        
        try:
            ret, frame = self._cap.read()
            
            if ret and frame is not None:
                return DecodedFrame(
                    ocv_image=frame,
                    width=frame.shape[1],
                    height=frame.shape[0],
                    frame_number=int(self._cap.get(cv2.CAP_PROP_POS_FRAMES)),
                    timestamp=time.time(),  # 使用解码时的当前时间
                    stream_id=self.video_stream.id
                )
            else:
                # 视频播放完毕，重新开始
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self._cap.read()
                
                if ret and frame is not None:
                    return DecodedFrame(
                        ocv_image=frame,
                        width=frame.shape[1],
                        height=frame.shape[0],
                        frame_number=int(self._cap.get(cv2.CAP_PROP_POS_FRAMES)),
                        timestamp=time.time(),  # 使用解码时的当前时间
                        stream_id=self.video_stream.id
                    )
                
                return None
                
        except Exception as e:
            print(f"读取视频文件帧失败: {e}")
            return None
    
    def is_opened(self) -> bool:
        """
        检查视频文件是否已打开
        
        Returns:
            bool: 是否已打开
        """
        return self._is_opened and self._cap is not None and self._cap.isOpened()
    
    def seek_to_frame(self, frame_number: int) -> bool:
        """
        跳转到指定帧
        
        Args:
            frame_number: 目标帧号
            
        Returns:
            bool: 是否成功跳转
        """
        if not self.is_opened():
            return False
        
        try:
            return self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        except Exception as e:
            print(f"跳转到帧 {frame_number} 失败: {e}")
            return False
    
    def get_total_frames(self) -> int:
        """
        获取视频总帧数
        
        Returns:
            int: 总帧数
        """
        if not self.is_opened():
            return 0
        
        try:
            return int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        except Exception:
            return 0
    
    def get_current_frame_number(self) -> int:
        """
        获取当前帧号
        
        Returns:
            int: 当前帧号
        """
        if not self.is_opened():
            return 0
        
        try:
            return int(self._cap.get(cv2.CAP_PROP_POS_FRAMES))
        except Exception:
            return 0
