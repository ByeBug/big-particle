"""
系统信号处理
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import SystemConfig

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SystemConfig)
def on_system_config_saved(sender, instance, created, **kwargs):
    """系统配置保存时的信号处理"""
    if instance.config_type == 'algorithm':
        if not created:
            logger.info(f"算法配置更新: {instance.name}")
            _update_algorithm_configs(instance.name, instance.config_data)


def _update_algorithm_configs(algo_name, dynamic_config):
    """更新运行中的算法配置"""
    try:
        from .stream.video_processor import active_processors
        
        # 遍历所有活跃的处理器
        # TODO 多机时不能这样处理，redis 消息队列？
        updated_count = 0
        for processor in active_processors.values():
            processor.update_algorithm_config(algo_name, dynamic_config)
            updated_count += 1
                
        logger.info(f"已更新 {updated_count} 个处理器中的算法 {algo_name} 配置")

    except:
        logger.exception(f"更新算法配置失败")
