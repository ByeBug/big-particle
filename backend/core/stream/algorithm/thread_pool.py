import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# 全局算法线程池，供所有算法共享
_algo_thread_pool = ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="algo-worker",
)

# 全局 IO 线程池，专门处理保存操作等IO密集任务
_io_thread_pool = ThreadPoolExecutor(
    max_workers=16,  # IO密集任务可以设置更多线程
    thread_name_prefix="io-worker",
)


def get_algo_thread_pool() -> ThreadPoolExecutor:
    """获取全局算法线程池实例"""
    return _algo_thread_pool


def get_io_thread_pool() -> ThreadPoolExecutor:
    """获取IO线程池实例"""
    return _io_thread_pool


def shutdown_algo_thread_pool(wait: bool = True):
    """关闭全局算法线程池"""
    logger.info("关闭全局算法线程池...")
    _algo_thread_pool.shutdown(wait=wait)
    logger.info("全局算法线程池已关闭")


def shutdown_io_thread_pool(wait: bool = True):
    """关闭IO线程池"""
    logger.info("关闭IO线程池...")
    _io_thread_pool.shutdown(wait=wait)
    logger.info("IO线程池已关闭")


def shutdown_all_thread_pools(wait: bool = True):
    """关闭所有线程池"""
    shutdown_algo_thread_pool(wait)
    shutdown_io_thread_pool(wait)


def get_thread_pool_status() -> dict:
    """获取线程池状态信息"""
    return {
        'algo_thread_pool': {
            'max_workers': _algo_thread_pool._max_workers,
            'active_threads': len(_algo_thread_pool._threads),
            'pending_tasks': _algo_thread_pool._work_queue.qsize() if hasattr(_algo_thread_pool, '_work_queue') else 0,
        },
        'io_thread_pool': {
            'max_workers': _io_thread_pool._max_workers,
            'active_threads': len(_io_thread_pool._threads),
            'pending_tasks': _io_thread_pool._work_queue.qsize() if hasattr(_io_thread_pool, '_work_queue') else 0,
        },
    }
