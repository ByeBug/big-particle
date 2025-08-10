import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# 全局线程池，供所有算法共享
_global_thread_pool = ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="algorithm-worker",
)


def get_global_thread_pool() -> ThreadPoolExecutor:
    """获取全局线程池实例"""
    return _global_thread_pool


def shutdown_global_thread_pool(wait: bool = True):
    """关闭全局算法线程池"""
    logger.info("关闭全局算法线程池...")
    _global_thread_pool.shutdown(wait=wait)
    logger.info("全局算法线程池已关闭")


def get_thread_pool_status() -> dict:
    """获取线程池状态信息"""
    return {
        'max_workers': _global_thread_pool._max_workers,
        'active_threads': len(_global_thread_pool._threads),
        'pending_tasks': _global_thread_pool._work_queue.qsize() if hasattr(_global_thread_pool, '_work_queue') else 0,
    }
