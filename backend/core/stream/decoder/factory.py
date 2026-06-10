"""
解码器工厂
"""

from ...models import VideoStream
from .base import BaseDecoder
from .mvs_decoder import MVSDecoder
from .video_file_decoder import VideoFileDecoder
from .image_dir_decoder import ImageDirDecoder
from .rtsp_decoder import RtspDecoder

class DecoderFactory:
    """解码器工厂类
    
    根据 VideoStream 的类型创建相应的解码器实例
    """
    
    # 解码器类型映射
    DECODER_MAPPING = {
        VideoStream.StreamType.RTSP: RtspDecoder,
        VideoStream.StreamType.MVS: MVSDecoder,
        VideoStream.StreamType.VIDEO_FILE: VideoFileDecoder,
        VideoStream.StreamType.IMAGE_DIR: ImageDirDecoder,
    }
    
    @classmethod
    def create_decoder(cls, video_stream: VideoStream) -> BaseDecoder:
        """
        创建解码器实例
        
        Args:
            video_stream: VideoStream 模型实例
            
        Returns:
            BaseDecoder: 解码器实例
            
        Raises:
            ValueError: 不支持的视频流类型
            ImportError: 缺少必要的依赖库
        """
        stream_type = video_stream.type
        
        if stream_type not in cls.DECODER_MAPPING:
            raise ValueError(f"不支持的视频流类型: {stream_type}")
        
        decoder_class = cls.DECODER_MAPPING[stream_type]
        
        try:
            return decoder_class(video_stream)
        except Exception as e:
            raise RuntimeError(f"创建 {stream_type} 解码器失败: {e}")
    
    @classmethod
    def get_supported_types(cls) -> list:
        """
        获取支持的视频流类型列表
        
        Returns:
            list: 支持的类型列表
        """
        return list(cls.DECODER_MAPPING.keys())
    
    @classmethod
    def is_type_supported(cls, stream_type: str) -> bool:
        """
        检查是否支持指定的视频流类型
        
        Args:
            stream_type: 视频流类型
            
        Returns:
            bool: 是否支持
        """
        return stream_type in cls.DECODER_MAPPING