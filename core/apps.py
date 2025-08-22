import signal
import sys
import os
import logging
import threading
import time

from django.apps import AppConfig


logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    
    def ready(self):
        """Django 启动完成后执行"""

        # 导入并注册 Django 信号
        from . import signals

        # 管理进程，不执行初始化逻辑
        if os.environ.get('RUN_MAIN') != 'true':
            return
        
        # 注册信号处理器，确保 Django 关闭时清理资源
        self._register_signal_handlers()
        
        # 启动初始化线程
        threading.Thread(target=self._delay_init, name='delay_init').start()
    
    def _delay_init(self):
        """延迟初始化，避免在 AppConfig.ready() 中访问数据库"""
        time.sleep(3)
        from .runtime import start_background_services
        start_background_services()
    
    def _register_signal_handlers(self):
        """注册信号处理器"""
        from .runtime import stop_background_services
        def shutdown_handler(signum, frame):
            """处理关闭信号"""
            logger.info(f"接收到信号 {signum}，正在关闭...")
            stop_background_services()
        
        # 注册常见的退出信号
        signal.signal(signal.SIGTERM, shutdown_handler)  # 终止信号
        signal.signal(signal.SIGINT, shutdown_handler)   # Ctrl+C
        
        # 在 Windows 上也注册 SIGBREAK
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, shutdown_handler)
