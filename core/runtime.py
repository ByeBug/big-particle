'''
启动和停止后台线程
'''
import threading
import logging

from core.stream.save_utils import start_cleanup_thread, stop_cleanup_thread
from core.stream.video_processor import shutdown_all_processors
from core.stream.algorithm.thread_pool import shutdown_all_thread_pools
from core.stream.algorithm.model.model_manager import ModelManager


logger = logging.getLogger(__name__)


_RUNTIME_STARTED = False
_RUNTIME_LOCK = threading.Lock()


def start_background_services():
    global _RUNTIME_STARTED
    with _RUNTIME_LOCK:
        if _RUNTIME_STARTED:
            return
        start_cleanup_thread()
        _init_default_configs()
        _start_enabled_streams()
        _RUNTIME_STARTED = True


def stop_background_services():
    with _RUNTIME_LOCK:
        logger.info("停止后台线程")
        shutdown_all_processors()
        ModelManager.cleanup_all()
        shutdown_all_thread_pools()
        stop_cleanup_thread()


def _init_default_configs():
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


def _start_enabled_streams():
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
