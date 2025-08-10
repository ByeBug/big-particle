"""
模型管理器 - 使用类变量管理模型单例
"""
import logging
import threading
from typing import Dict, Any, Type

logger = logging.getLogger(__name__)


class ModelManager:
    """模型管理器 - 使用类变量管理各种类型的模型单例"""
    
    # 类变量：存储所有模型实例
    _models: Dict[str, Any] = {}  # {model_path: model_instance}
    _model_lock = threading.Lock()
    
    @classmethod
    def get_model(cls, model_class: Type, model_path: str, **kwargs) -> Any:
        """
        获取模型实例，如果不存在则创建
        
        Args:
            model_class: 模型类，如 PaddleDetector
            model_path: 模型路径，用作唯一标识
            **kwargs: 模型初始化参数
            
        Returns:
            模型实例
        """
        with cls._model_lock:
            if model_path not in cls._models:
                logger.info(f"创建新的模型实例: {model_class.__name__} - {model_path}")
                cls._models[model_path] = model_class(model_path, **kwargs)
            else:
                logger.debug(f"复用现有模型实例: {model_path}")
            
            return cls._models[model_path]
    
    @classmethod
    def remove_model(cls, model_path: str):
        """
        移除模型实例
        
        Args:
            model_path: 模型路径
        """
        with cls._model_lock:
            if model_path in cls._models:
                logger.info(f"移除模型实例: {model_path}")
                # 如果模型有 cleanup 方法，先调用
                if hasattr(cls._models[model_path], 'cleanup'):
                    cls._models[model_path].cleanup()
                del cls._models[model_path]
    
    @classmethod
    def cleanup_all(cls):
        """清理所有模型实例"""
        with cls._model_lock:
            logger.info(f"清理所有模型实例，共 {len(cls._models)} 个")
            # 如果模型有 cleanup 方法，遍历调用
            for model in cls._models.values():
                if hasattr(model, 'cleanup'):
                    model.cleanup()
            cls._models.clear()
    
    @classmethod
    def get_model_count(cls) -> int:
        """获取当前模型实例数量"""
        with cls._model_lock:
            return len(cls._models)
