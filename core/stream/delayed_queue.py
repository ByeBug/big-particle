import time
import queue


class DelayedQueue:
    """延时队列：元素入队后需等待指定时间才能出队"""
    
    def __init__(self, delay_seconds: float = 0.5, maxsize: int = 0):
        self.delay = delay_seconds
        self.queue = queue.Queue(maxsize=maxsize)
    
    def put(self, item):
        """将元素加入队列"""
        enqueue_time = time.time()
        self.queue.put((enqueue_time, item))
    
    def put_nowait(self, item):
        """非阻塞方式将元素加入队列，队列满时抛出 queue.Full 异常"""
        enqueue_time = time.time()
        self.queue.put_nowait((enqueue_time, item))
    
    def get(self):
        """获取元素，如果未到延时时间则等待"""
        while True:
            enqueue_time, item = self.queue.get()
            now = time.time()
            elapsed = now - enqueue_time
            
            if elapsed >= self.delay:
                return item
            else:
                # 提前1ms唤醒，避免调度延迟导致的超时
                remaining = self.delay - elapsed - 0.001
                if remaining > 0:
                    time.sleep(remaining)
                return item
