"""
视频流日志工具
"""

import logging


class StreamLoggerAdapter(logging.LoggerAdapter):
    """带StreamId标识的日志适配器
    
    在日志消息前添加 [Stream:{stream_id}] 前缀，
    便于在多视频流环境中区分不同流的日志输出。
    """
    
    def process(self, msg, kwargs):
        return f"[Stream:{self.extra['stream_id']}] {msg}", kwargs