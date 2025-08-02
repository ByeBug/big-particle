"""
图像目录解码器
"""

import os
import glob
import time
import cv2
from typing import Optional, List

from .base import BaseDecoder
from ..frame import DecodedFrame


class ImageDirDecoder(BaseDecoder):
    """图像目录解码器
    
    用于从图像目录读取图片文件作为帧数据
    """
    
    # 支持的图像格式
    SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}
    
    def __init__(self, video_stream, fps: Optional[int] = None):
        super().__init__(video_stream, fps)
        self._image_files: List[str] = []
        self._current_index = 0
    
    def open(self) -> bool:
        """
        打开图像目录
        
        Returns:
            bool: 是否成功打开
        """
        try:
            if self._is_opened:
                return True
            
            dir_path = self.video_stream.address
            if not dir_path:
                print("图像目录地址不能为空")
                return False
            
            if not os.path.exists(dir_path):
                print(f"图像目录不存在: {dir_path}")
                return False
            
            if not os.path.isdir(dir_path):
                print(f"路径不是目录: {dir_path}")
                return False
            
            # 查找所有支持的图像文件
            self._image_files = []
            for ext in self.SUPPORTED_EXTENSIONS:
                pattern = os.path.join(dir_path, f"*{ext}")
                self._image_files.extend(glob.glob(pattern))
                # 同时搜索大写扩展名
                pattern = os.path.join(dir_path, f"*{ext.upper()}")
                self._image_files.extend(glob.glob(pattern))
            
            # 排序确保顺序一致
            self._image_files.sort()
            
            if not self._image_files:
                print(f"目录中未找到支持的图像文件: {dir_path}")
                print(f"支持的格式: {', '.join(self.SUPPORTED_EXTENSIONS)}")
                return False
            
            # 读取第一张图片获取尺寸信息
            first_image = cv2.imread(self._image_files[0])
            if first_image is None:
                print(f"无法读取第一张图像: {self._image_files[0]}")
                return False
            
            # 更新实例属性
            if not self.width:
                self.width = first_image.shape[1]
            if not self.height:
                self.height = first_image.shape[0]
            
            self._current_index = 0
            self._is_opened = True
            self.reset_stats()
            
            print(f"成功打开图像目录: {dir_path}")
            print(f"找到 {len(self._image_files)} 张图像，尺寸: {self.width}x{self.height}")
            
            return True
            
        except Exception as e:
            print(f"打开图像目录失败: {e}")
            return False
    
    def close(self):
        """
        关闭图像目录
        """
        try:
            self._image_files.clear()
            self._current_index = 0
            self._is_opened = False
            
            print(f"成功关闭图像目录: {self.video_stream.address}")
            
        except Exception as e:
            print(f"关闭图像目录失败: {e}")
    
    def read_frame(self) -> Optional[DecodedFrame]:
        """
        从图像目录读取一张图片
        
        Returns:
            Optional[DecodedFrame]: 解码帧对象，失败返回 None
        """
        if not self._is_opened or not self._image_files:
            return None
        
        try:
            # 获取当前图像文件路径
            current_file = self._image_files[self._current_index]
            
            # 读取图像
            image = cv2.imread(current_file)
            
            if image is None:
                print(f"无法读取图像: {current_file}")
                # 跳到下一张图像
                self._current_index = (self._current_index + 1) % len(self._image_files)
                return None
            
            # 获取当前图像索引作为帧号
            current_frame_number = self._current_index
            
            # 准备下一张图像的索引（循环播放）
            self._current_index = (self._current_index + 1) % len(self._image_files)
            
            # 使用当前时间戳作为时间戳
            timestamp = time.time()
            
            return DecodedFrame(
                ocv_image=image,
                width=image.shape[1],
                height=image.shape[0],
                frame_number=current_frame_number,
                timestamp=timestamp,
                stream_id=self.video_stream.id
            )
                
        except Exception as e:
            print(f"读取图像目录帧失败: {e}")
            return None
    
    def is_opened(self) -> bool:
        """
        检查图像目录是否已打开
        
        Returns:
            bool: 是否已打开
        """
        return self._is_opened
    
    def seek_to_image(self, index: int) -> bool:
        """
        跳转到指定图像索引
        
        Args:
            index: 目标图像索引
            
        Returns:
            bool: 是否成功跳转
        """
        if not self.is_opened():
            return False
        
        if 0 <= index < len(self._image_files):
            self._current_index = index
            return True
        
        return False
    
    def get_total_images(self) -> int:
        """
        获取图像总数
        
        Returns:
            int: 图像总数
        """
        return len(self._image_files) if self._is_opened else 0
    
    def get_current_index(self) -> int:
        """
        获取当前图像索引
        
        Returns:
            int: 当前图像索引
        """
        return self._current_index if self._is_opened else 0
    
    def get_current_file(self) -> Optional[str]:
        """
        获取当前图像文件路径
        
        Returns:
            Optional[str]: 当前图像文件路径
        """
        if not self.is_opened() or self._current_index >= len(self._image_files):
            return None
        
        return self._image_files[self._current_index]
    
    def get_image_list(self) -> List[str]:
        """
        获取所有图像文件列表
        
        Returns:
            List[str]: 图像文件路径列表
        """
        return self._image_files.copy() if self._is_opened else []
