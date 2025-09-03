import logging
import os
import threading
import time
from queue import Full, Queue, Empty
from collections import defaultdict
from typing import Dict, List

import paddle
from paddle.inference import Config
from paddle.inference import create_predictor
import yaml
import numpy as np
import cv2

from .instance import Instance
from .preprocess import Resize, NormalizeImage, Permute
from core.stream.frame import DecodedFrame

logger = logging.getLogger(__name__)


class PaddleDetector:
    '''Paddle 检测模型'''
    
    def __init__(self, model_path: str, max_batch_size: int):
        '''初始化 Paddle 检测模型'''
        self.model_path = os.path.normpath(model_path)
        self.model_name = self.model_path.split('/')[-1]
        self.max_batch_size = max_batch_size
        self.threshold = 0.5    # 模型阈值固定为 0.5
        
        # 流队列字典 {stream_id: Queue}
        self.stream_queues: Dict[int, Queue] = defaultdict(lambda: Queue(maxsize=10))

        paddle.enable_static()

        deploy_file = os.path.join(self.model_path, 'infer_cfg.yml')
        if not os.path.exists(deploy_file):
            raise FileNotFoundError(f"模型配置文件不存在: {deploy_file}")
        with open(deploy_file, 'r') as f:
            yml_conf = yaml.safe_load(f)
        
        self.mask = False
        if 'mask' in yml_conf:
            self.mask = yml_conf['mask']
        self.label_list = yml_conf['label_list']

        infer_model = os.path.join(self.model_path, 'model.pdmodel')
        infer_params = os.path.join(self.model_path, 'model.pdiparams')
        self.config = Config(infer_model, infer_params)
        self.config.enable_use_gpu(200, 0)
        self.config.switch_ir_optim(True)
        self.config.enable_tensorrt_engine(
            workspace_size=15 * 1024 * 1024 * 1024,     # 15GB，仅在生成 trt 模型时生效
            max_batch_size=8,
            min_subgraph_size=yml_conf['min_subgraph_size'],
            precision_mode=Config.Precision.Half,
            use_static=True,        # 默认使用 trt 缓存模型
            use_calib_mode=False
        )
        min_input_shape = {
            'image': [1, 3, 640, 640],
            'scale_factor': [1, 2]
        }
        max_input_shape = {
            'image': [8, 3, 640, 640],
            'scale_factor': [8, 2]
        }
        opt_input_shape = {
            'image': [4, 3, 640, 640],
            'scale_factor': [4, 2]
        }
        self.config.set_trt_dynamic_shape_info(min_input_shape, max_input_shape,
                                            opt_input_shape)
        # disable print log when predict
        self.config.disable_glog_info()
        # enable shared memory
        self.config.enable_memory_optim()
        # disable feed, fetch OP, needed by zero_copy_run
        self.config.switch_use_feed_fetch_ops(False)
        self.predictor = create_predictor(self.config)

        self.preprocess_ops = []
        for op_info in yml_conf['Preprocess']:
            new_op_info = op_info.copy()
            op_type = new_op_info.pop('type')
            self.preprocess_ops.append(eval(op_type)(**new_op_info))

        # 线程控制
        self.running = False
        self.infer_thread = None
        
        # 启动推理线程
        self.start_infer_thread()

        logger.info(f"已初始化 PaddleDetector: {self.model_name}, max_batch_size={self.max_batch_size}")
    
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
                
                # 按 max_batch_size 分批处理
                for i in range(0, len(frames_to_process), self.max_batch_size):
                    batch_frames = frames_to_process[i:i + self.max_batch_size]
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
            
            self._preprocess_batch(batch_frames)
            batch_result = self._predict_batch()
            batch_im_instances = self._postprocess_batch(batch_result)
            
            # 设置每帧的推理结果
            for frame, im_instances in zip(batch_frames, batch_im_instances):
                frame.model_results[self.model_name] = im_instances
                frame.model_events[self.model_name].set()
            
            logger.debug(f"批量推理完成: batch_size={len(batch_frames)}")
            
        except Exception as e:
            logger.exception(f"批量推理失败: {e}")
            
            # 失败时也要触发完成事件
            for frame in batch_frames:
                frame.model_events[self.model_name].set()

    def _preprocess_batch(self, batch_frames: List[DecodedFrame]):
        """预处理一批帧"""
        batch_imgs = []
        batch_img_shapes = []
        batch_scale_factors = []
        for frame in batch_frames:
            # 推理需要 RGB 格式 TODO 将 RGB 格式缓存到帧内
            im = cv2.cvtColor(frame.ocv_image, cv2.COLOR_BGR2RGB)
            im_info = {
                'im_shape': np.array(im.shape[:2], dtype=np.float32),
                'scale_factor': np.array([1., 1.], dtype=np.float32),
            }
            # 顺序执行预处理步骤
            for operator in self.preprocess_ops:
                im, im_info = operator(im, im_info)
            
            batch_imgs.append(im)
            batch_img_shapes.append(im_info['im_shape'])
            batch_scale_factors.append(im_info['scale_factor'])
        
        inputs = {
            'image': np.stack(batch_imgs).astype('float32'),
            'im_shape': np.array(batch_img_shapes, dtype='float32'),
            'scale_factor': np.array(batch_scale_factors, dtype='float32')
        }

        input_names = self.predictor.get_input_names()
        for i in range(len(input_names)):
            input_tensor = self.predictor.get_input_handle(input_names[i])
            if input_names[i] == 'x':
                input_tensor.copy_from_cpu(inputs['image'])
            else:
                input_tensor.copy_from_cpu(inputs[input_names[i]])

    def _predict_batch(self):
        """推理帧"""
        self.predictor.run()

        output_names = self.predictor.get_output_names()
        
        boxes_tensor = self.predictor.get_output_handle(output_names[0])
        np_boxes = boxes_tensor.copy_to_cpu()
        
        if len(output_names) == 1:
            # some exported model can not get tensor 'bbox_num' 
            np_boxes_num = np.array([len(np_boxes)])
        else:
            boxes_num = self.predictor.get_output_handle(output_names[1])
            np_boxes_num = boxes_num.copy_to_cpu()
        
        result = {
            # shape: [N, 6]，每个元素：[class, score, x_min, y_min, x_max, y_max]
            'boxes': np_boxes,
            # shape: [N,]，每个元素：每张图片的检测框数量
            'boxes_num': np_boxes_num,
        }

        if self.mask:
            masks_tensor = self.predictor.get_output_handle(output_names[2])
            np_masks = masks_tensor.copy_to_cpu()
            result['masks'] = np_masks
        
        return result

    def _postprocess_batch(self, batch_result: Dict[str, np.ndarray]):
        """后处理帧"""
        batch_im_instances = []
        start_idx = 0
        for boxes_num in batch_result['boxes_num']:
            im_instances = []
            # 获取一批中单张图片的检测框
            im_boxes = batch_result['boxes'][start_idx:start_idx + boxes_num, :]
            # 过滤检测框
            expect_boxes = (im_boxes[:, 1] > self.threshold) & (im_boxes[:, 0] > -1)
            im_boxes = im_boxes[expect_boxes, :]

            for box in im_boxes:
                clsid, score, bbox = int(box[0]), round(float(box[1]), 2), box[2:]
                # 模型输出的坐标已经是原图的尺寸
                xmin, ymin, xmax, ymax = bbox
                im_instances.append(Instance(clsid, self.label_list[clsid], score,
                    left=round(xmin), top=round(ymin), right=round(xmax), bottom=round(ymax)))
            
            batch_im_instances.append(im_instances)
            
            # 调整索引获取下一张图的检测框
            start_idx += boxes_num
        
        return batch_im_instances

    def cleanup(self):
        """清理资源"""
        self.stop_infer_thread()
        
        # 清理队列
        self.stream_queues.clear()
        
        logger.info(f"已清理: {self.model_name}")
