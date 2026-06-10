'''
opencv 解码 rtsp 流测试
'''
import logging
import os

import cv2

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


rtsp_url = 'rtsp://admin:vlt99%40WG@192.168.1.103:554/Streaming/Channels/101'
output_dir = 'data/decode_from_101'
os.makedirs(output_dir, exist_ok=True)

cap = cv2.VideoCapture(rtsp_url)
if not cap.isOpened():
    logging.error(f'无法打开流：{rtsp_url}')
    exit(1)

logging.info(f'打开流：{rtsp_url}')

logging.info(f'帧率：{cap.get(cv2.CAP_PROP_FPS)}')
logging.info(f'宽度：{cap.get(cv2.CAP_PROP_FRAME_WIDTH)}')
logging.info(f'高度：{cap.get(cv2.CAP_PROP_FRAME_HEIGHT)}')
logging.info(f'格式：{cap.get(cv2.CAP_PROP_FORMAT)}')

count = 20
for i in range(count):
    ret, frame = cap.read()
    if not ret:
        logging.error('读取失败')
        break
    
    filename = f'{output_dir}/frame_{i:03d}.png'
    cv2.imwrite(filename, frame)
    logging.info(f'保存帧：{filename}')

cap.release()
logging.info(f'关闭流：{rtsp_url}')
