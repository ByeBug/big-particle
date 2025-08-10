from enum import Enum


class InferStatus(Enum):
    """推理状态枚举"""
    NEED_INFER = "need_infer"  # 需要推理
    NEED_RENDER = "need_render"  # 需要渲染
    DONE = "done"  # 完成
    FAILED = "failed"  # 失败
