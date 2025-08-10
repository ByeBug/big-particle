import logging
import os
import threading
import time
from queue import Full, Queue, Empty
from collections import defaultdict
from typing import Dict, List

from core.stream.frame import DecodedFrame

logger = logging.getLogger(__name__)


class PaddleDetector:
    '''Paddle 检测模型'''
    
    def __init__(self, model_path: str, batch_size: int):
        '''初始化 Paddle 检测模型'''
        self.model_path = os.path.normpath(model_path)
        self.model_name = self.model_path.split('/')[-1]
        self.batch_size = batch_size
        
        # 流队列字典 {stream_id: Queue}
        self.stream_queues: Dict[int, Queue] = defaultdict(lambda: Queue(maxsize=10))

        # 线程控制
        self.running = False
        self.infer_thread = None
        
        # 启动推理线程
        self.start_infer_thread()

        logger.info(f"初始化 PaddleDetector: {self.model_name}, batch_size={self.batch_size}")
    
    def start_infer_thread(self):
        """启动推理线程"""
        if self.running:
            return
        
        self.running = True
        self.infer_thread = threading.Thread(
            target=self.infer_loop, 
            name=f"infer-{self.model_name}"
        )
        self.infer_thread.start()
        logger.info(f"推理线程已启动: {self.infer_thread.name}")
    
    def stop_infer_thread(self):
        """停止推理线程"""
        if not self.running:
            return
        
        self.running = False
        if self.infer_thread and self.infer_thread.is_alive():
            self.infer_thread.join(timeout=5.0)
            if self.infer_thread.is_alive():
                logger.warning(f"推理线程未能在5秒内正常结束: {self.infer_thread.name}")
            else:
                logger.info(f"推理线程已停止: {self.infer_thread.name}")
    
    def submit_frame(self, frame: DecodedFrame):
        """
        提交帧到对应流的队列
        
        Args:
            frame: 待处理的帧
        """
        # 创建完成事件
        completion_event = threading.Event()
        frame.model_events[self.model_name] = completion_event
        
        try:
            # 加入流队列（非阻塞）
            self.stream_queues[frame.stream_id].put_nowait(frame)
            logger.debug(f"帧已加入队列: model: {self.model_name}, stream: {frame.stream_id}")
            return True
        except Full:
            logger.error(f"队列满: model: {self.model_name}, stream: {frame.stream_id}")
            return False
    
    def infer_loop(self):
        """推理线程主循环"""
        while self.running:
            try:
                # 从每个流队列中收集帧
                frames_to_process = []
                
                # 遍历所有流队列
                for queue in self.stream_queues.values():
                    try:
                        # 从每个队列取第一帧（非阻塞）
                        frame = queue.get_nowait()
                        frames_to_process.append(frame)
                    except Empty:
                        continue
                
                if not frames_to_process:
                    time.sleep(0.01)  # 没有帧时休眠 10ms
                    continue
                
                # 按 batch_size 分批处理
                for i in range(0, len(frames_to_process), self.batch_size):
                    batch_frames = frames_to_process[i:i + self.batch_size]
                    self.process_batch(batch_frames)
                
            except Exception as e:
                logger.error(f"推理线程错误: {e}")
                time.sleep(0.1)
    
    def process_batch(self, batch_frames: List[DecodedFrame]):
        """
        处理一批帧
        
        Args:
            batch_frames: 帧列表
        """
        try:
            logger.debug(f"开始批量推理: batch_size={len(batch_frames)}")
            
            # TODO: 实现实际的批量推理逻辑
            # 这里暂时模拟推理时间
            time.sleep(0.01 * len(batch_frames))  # 模拟推理时间
            
            # 设置每帧的推理结果
            for frame in batch_frames:
                # 模拟推理结果
                result = {
                    'detections': [],  # 空的检测结果
                    'inference_time': 0.05,
                    'model_path': self.model_path
                }
                
                # 将结果设置到帧上
                frame.model_results[self.model_name] = result
                frame.model_events[self.model_name].set()
            
            logger.debug(f"批量推理完成: batch_size={len(batch_frames)}")
            
        except Exception as e:
            logger.error(f"批量推理失败: {e}")
            
            # 失败时也要触发完成事件
            for frame in batch_frames:
                frame.model_events[self.model_name].set()
    
    def cleanup(self):
        """清理资源"""
        self.stop_infer_thread()
        
        # 清理队列
        self.stream_queues.clear()
        
        logger.info(f"已清理: {self.model_name}")
