'''
通过 onvif 获取抓拍 url，并下载抓拍图片。
依赖：onvif_zeep, requests
'''
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
snapshot_uri = snapshot.Uri
print("Snapshot URI:", snapshot_uri)

stream_uri = media.GetStreamUri({
    'StreamSetup': {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}},
    'ProfileToken': profile.token})
rtsp_uri = stream_uri.Uri
print("Stream URI:", rtsp_uri)

r = requests.get(snapshot_uri, auth=HTTPDigestAuth(USER, PASS), timeout=5)
r.raise_for_status()
with open('snapshot.jpg','wb') as f:
    f.write(r.content)
print("Saved snapshot.jpg")
