"""
模型包，其中包含各种算法模型
"""
from .paddle_detector import PaddleDetector
from .model_manager import ModelManager

__all__ = ['PaddleDetector', 'ModelManager']
