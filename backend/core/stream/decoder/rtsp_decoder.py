"""
RTSP 解码器
"""

import time
import logging
import cv2
from typing import Optional
from urllib.parse import quote

from .base import BaseDecoder
from ..frame import DecodedFrame
from ..logging_utils import StreamLoggerAdapter

logger = logging.getLogger(__name__)


class RtspDecoder(BaseDecoder):
    """RTSP 解码器
    
    用于从 RTSP 流读取帧数据
    """
    
    def __init__(self, video_stream):
        super().__init__(video_stream)
        self._cap = None
        
        # 带 stream_id 的logger
        self.logger = StreamLoggerAdapter(logger, {'stream_id': video_stream.id})
    
    def open(self) -> bool:
        """
        打开 RTSP 流
        
        Returns:
            bool: 是否成功打开
        """
        try:
            if self._is_opened:
                return True
            
            rtsp_url = self.video_stream.address
            if not rtsp_url:
                self.logger.error("RTSP 地址不能为空")
                return False
            
            # 对 RTSP URL 中的用户名密码进行 URL 编码处理
            processed_url = self._encode_rtsp_credentials(rtsp_url)
            
            # 打开 RTSP 流
            self._cap = cv2.VideoCapture(processed_url)
            
            if not self._cap.isOpened():
                self.logger.error(f"无法打开 RTSP 流: {rtsp_url}")
                return False
            
            # 获取视频信息
            video_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            video_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # RTSP流的帧率可能不准确，优先使用配置的fps
            video_fps = int(round(self._cap.get(cv2.CAP_PROP_FPS)))
            if video_fps <= 0:
                video_fps = self.video_stream.fps or 30  # 默认30fps
            
            # 更新实例属性
            self.width = video_width
            self.height = video_height
            self.fps = video_fps
            
            # 更新了 fps 要重新设置 interval
            self._target_interval = 1.0 / self.fps if self.fps else 0.1
            
            self._is_opened = True
            self.reset_stats()
            
            self.logger.info(f"成功打开 RTSP 流: {rtsp_url}")
            self.logger.info(f"视频信息: {video_width}x{video_height}, {video_fps}fps")
            
            return True
            
        except Exception as e:
            self.logger.error(f"打开 RTSP 流失败: {e}")
            return False
    
    def close(self):
        """
        关闭 RTSP 流
        """
        try:
            if self._cap:
                self._cap.release()
                self.logger.info(f"成功关闭 RTSP 流: {self.video_stream.address}")
            
            self._cap = None
            self._is_opened = False
            
        except Exception as e:
            self.logger.error(f"关闭 RTSP 流失败: {e}")
    
    def read_frame(self) -> Optional[DecodedFrame]:
        """
        从 RTSP 流读取一帧
        
        Returns:
            Optional[DecodedFrame]: 解码帧对象，失败返回 None
        """
        if not self._is_opened or not self._cap:
            return None
        
        ret, frame = self._cap.read()
        
        if ret and frame is not None:
            return DecodedFrame(
                ocv_image=frame,
                width=frame.shape[1],
                height=frame.shape[0],
                frame_number=self._frame_count,
                timestamp=int(time.time() * 1000),  # 使用解码时的当前时间
                stream_id=self.video_stream.id,
                stream_name=self.video_stream.name
            )
        else:
            raise Exception("RTSP流读取失败，可能是网络问题或流断开")
    
    def is_opened(self) -> bool:
        """
        检查 RTSP 流是否已打开
        
        Returns:
            bool: 是否已打开
        """
        return self._is_opened and self._cap is not None and self._cap.isOpened()
    
    def _encode_rtsp_credentials(self, rtsp_url: str) -> str:
        """
        对RTSP URL中的用户名密码进行URL编码
        
        Args:
            rtsp_url: 原始RTSP URL
            
        Returns:
            str: 处理后的RTSP URL
        """
        if '@' not in rtsp_url:
            return rtsp_url
        
        try:
            # 分离协议和其余部分
            scheme_end = rtsp_url.find('://') + 3
            scheme_part = rtsp_url[:scheme_end]  # "rtsp://"
            remaining_part = rtsp_url[scheme_end:]
            
            # 从最后一个@分离认证信息和主机部分
            auth_end = remaining_part.rfind('@')
            auth_part = remaining_part[:auth_end]  # "user:password"
            host_part = remaining_part[auth_end + 1:]  # "host:port/path"
            
            # 对认证部分进行URL编码（但保留:分隔符）
            if ':' in auth_part:
                user, password = auth_part.split(':', 1)
                encoded_auth = f"{quote(user, safe='')}:{quote(password, safe='')}"
            else:
                encoded_auth = quote(auth_part, safe='')
            
            # 重新组装URL
            return f"{scheme_part}{encoded_auth}@{host_part}"
            
        except Exception as e:
            self.logger.warning(f"URL编码处理失败，使用原始URL: {e}")
            return rtsp_url
