"""
CountDownLatch 实现
"""
import threading


class CountDownLatch:
    """CountDownLatch - 等待多个任务完成"""
    
    def __init__(self, count: int):
        """
        初始化 CountDownLatch
        
        Args:
            count: 初始计数值
        """
        if count < 0:
            raise ValueError("计数不能为负")
        
        self._count = count
        self._lock = threading.Lock()
        self._event = threading.Event()
        
        # 如果初始计数为0，立即设置事件
        if count == 0:
            self._event.set()
    
    def count_down(self):
        """将计数减 1，当计数达到 0 时释放所有等待的线程"""
        with self._lock:
            if self._count > 0:
                self._count -= 1
                if self._count == 0:
                    self._event.set()
    
    def wait(self, timeout: float = None) -> bool:
        """
        等待计数达到0
        
        Args:
            timeout: 超时时间（秒），None 表示无限等待
            
        Returns:
            bool: True 表示计数达到0，False 表示超时
        """
        return self._event.wait(timeout)
    
    def get_count(self) -> int:
        """获取当前计数值"""
        with self._lock:
            return self._count
