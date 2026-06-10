'''
通过 onvif 获取抓拍 url，并收集图片。
'''
import os
import datetime

from onvif import ONVIFCamera
import requests
from requests.auth import HTTPDigestAuth

CAM_IP = '192.168.1.103'
PORT = 80
USER = 'admin'
PASS = 'vlt99@WG'

# 1. 连接摄像头
cam = ONVIFCamera(CAM_IP, PORT, USER, PASS)

# 2. 建立 media service，拿 profiles
media = cam.create_media_service()
profiles = media.GetProfiles()
profile = profiles[0]   # 根据需要选择合适的 profile

# 3. 获取 snapshot URI
snapshot = media.GetSnapshotUri({'ProfileToken': profile.token})
uri = snapshot.Uri
print("Snapshot URI:", uri)

save_dir = 'onvif_collected_imgs'
os.makedirs(save_dir, exist_ok=True)

count = 50
for i in range(count):
    r = requests.get(uri, auth=HTTPDigestAuth(USER, PASS), timeout=5)
    r.raise_for_status()
    
    now = datetime.datetime.now()
    filename = now.strftime('%Y%m%d_%H%M%S.%f')[:-3] + '.jpg'
    file_path = os.path.join(save_dir, filename)
    with open(file_path,'wb') as f:
        f.write(r.content)
    print(f"Saved {file_path}")
