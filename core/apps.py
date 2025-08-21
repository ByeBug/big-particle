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

        # 管理进程，不执行初始化逻辑
        if os.environ.get('RUN_MAIN') != 'true':
            return
        
        # 注册信号处理器，确保 Django 关闭时清理资源
        self._register_signal_handlers()
        
        # 导入并注册 Django 信号
        from . import signals
        
        # 启动初始化线程
        threading.Thread(target=self._delay_init, name='delay_init').start()
    
    def _delay_init(self):
        """延迟初始化，避免在 AppConfig.ready() 中访问数据库"""
        time.sleep(3)
        from .stream.save_utils import start_cleanup_thread
        start_cleanup_thread()
        self._init_default_configs()
        self._start_enabled_streams()

    def _init_default_configs(self):
        """初始化默认系统配置"""
        try:
            from .models import SystemConfig
            
            # 创建大颗粒算法配置
            _, created = SystemConfig.objects.get_or_create(
                config_type='algorithm',
                name='big_particle',
                defaults={
                    'description': '大颗粒检测算法配置',
                    'config_data': {
                        'threshold': 0.7,       # 模型阈值
                        'alarm_threshold': [    # 不同等级的告警阈值
                            {'size_level': 28, 'warning': 30, 'error': 50},
                            {'size_level': 32, 'warning': 10, 'error': 20},
                            {'size_level': 50, 'warning': 1, 'error': 10},
                        ]
                    },
                    'is_active': True
                }
            )
            
            if created:
                logger.info("已创建大颗粒算法默认配置")
            else:
                logger.debug("大颗粒算法配置已存在")
                
        except:
            logger.exception(f"初始化默认配置失败")
    
    def _register_signal_handlers(self):
        """注册信号处理器"""
        # 惰性导入，避免在 App 未就绪时导入引用 models 的模块
        from .stream.video_processor import shutdown_all_processors
        from .stream.algorithm.thread_pool import shutdown_all_thread_pools
        from .stream.save_utils import stop_cleanup_thread
        def shutdown_handler(signum, frame):
            """处理关闭信号"""
            logger.info(f"接收到信号 {signum}，正在关闭...")
            try:
                shutdown_all_thread_pools()
                stop_cleanup_thread()
                shutdown_all_processors()
            except:
                logger.exception(f"关闭时出错")
            
            logging.shutdown()
            sys.exit(0)
        
        # 注册常见的退出信号
        signal.signal(signal.SIGTERM, shutdown_handler)  # 终止信号
        signal.signal(signal.SIGINT, shutdown_handler)   # Ctrl+C
        
        # 在 Windows 上也注册 SIGBREAK
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, shutdown_handler)

    def _start_enabled_streams(self):
        """启动所有启用的视频流"""
        try:
            logger.info("服务启动：加载并启动所有启用的视频流")
            from .models import VideoStream
            from .stream.video_processor import create_processor, get_processor

            enabled_streams = list(VideoStream.objects.filter(enabled=True))
            total = len(enabled_streams)
            started = 0

            for stream in enabled_streams:
                try:
                    processor = get_processor(stream.id)
                    if processor and processor.is_running():
                        logger.info(f"视频流处理器已在运行: {stream.id}")
                        continue
                    create_processor(stream)
                    started += 1
                except Exception as e:
                    logger.error(f"启动视频流 {stream.id} 失败: {e}")

            logger.info(f"服务启动：成功启动 {started}/{total} 个视频流")
        except Exception:
            logger.exception("服务启动时加载并启动视频流失败")
