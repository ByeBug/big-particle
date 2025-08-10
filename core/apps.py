import signal
import sys
import os
import logging
from django.apps import AppConfig


logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    
    def ready(self):
        """Django 启动完成后执行"""

        # 管理进程，不执行初始化逻辑
        if os.environ.get('RUN_MAIN') != 'true':
            return
        
        # 注册信号处理器，确保 Django 关闭时清理资源
        self._register_signal_handlers()
        
        # 导入模型和处理器
        from .models import VideoStream
        from .stream.video_processor import create_processor, start_cleanup_thread
        
        # TODO 服务启动时加载并启动所有启用的视频流

        try:
            start_cleanup_thread()
        except Exception as e:
            logger.error(f"启动清理线程失败: {e}")
    
    def _register_signal_handlers(self):
        """注册信号处理器"""
        # 惰性导入，避免在 App 未就绪时导入引用 models 的模块
        from .stream.video_processor import shutdown_all_processors
        from .stream.algorithm.thread_pool import shutdown_global_thread_pool
        def shutdown_handler(signum, frame):
            """处理关闭信号"""
            logger.info(f"接收到信号 {signum}，正在关闭...")
            try:
                shutdown_all_processors()
                shutdown_global_thread_pool()
            except Exception as e:
                logger.error(f"关闭时出错: {e}")
            
            # 调用默认的退出处理
            sys.exit(0)
        
        # 注册常见的退出信号
        signal.signal(signal.SIGTERM, shutdown_handler)  # 终止信号
        signal.signal(signal.SIGINT, shutdown_handler)   # Ctrl+C
        
        # 在 Windows 上也注册 SIGBREAK
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, shutdown_handler)
