'''
ONVIF 摄像头快照性能测试脚本
依赖：onvif_zeep, requests
'''
from onvif import ONVIFCamera
import requests
from requests.auth import HTTPDigestAuth
import time
import statistics

CAM_IP = '192.168.1.103'
PORT = 80
USER = 'admin'
PASS = 'vlt99@WG'

def get_snapshot_uri():
    """获取摄像头快照URI"""
    try:
        # 1. 连接摄像头
        cam = ONVIFCamera(CAM_IP, PORT, USER, PASS)
        
        # 2. 建立 media service，拿 profiles
        media = cam.create_media_service()
        profiles = media.GetProfiles()
        profile = profiles[0]   # 根据需要选择合适的 profile
        
        # 3. 获取 snapshot URI
        snapshot = media.GetSnapshotUri({'ProfileToken': profile.token})
        uri = snapshot.Uri
        
        return uri
    except Exception as e:
        print(f"获取快照URI失败: {e}")
        return None

def performance_test(uri, total_requests=100):
    """执行性能测试"""
    
    # 统计变量
    successful_requests = 0
    failed_requests = 0
    response_times = []
    
    # 开始计时
    start_time = time.time()
    
    for i in range(total_requests):
        request_start = time.time()
        
        try:
            # 发送请求
            # 即使使用 session 复用，性能也没有明显提升，因此直接请求
            r = requests.get(uri, auth=HTTPDigestAuth(USER, PASS), timeout=5)
            r.raise_for_status()
            
            # 记录响应时间
            request_time = time.time() - request_start
            response_times.append(request_time)
            successful_requests += 1
            
            # 每50次请求显示进度
            if (i + 1) % 50 == 0:
                elapsed = time.time() - start_time
                current_rps = (i + 1) / elapsed
                print(f"进度: {i + 1}/{total_requests} | 当前RPS: {current_rps:.2f} | 成功: {successful_requests} | 失败: {failed_requests}")
                
        except Exception as e:
            failed_requests += 1
            if failed_requests <= 5:  # 只显示前5个错误
                print(f"请求 {i + 1} 失败: {e}")
    
    # 结束计时
    total_time = time.time() - start_time
    
    # 计算统计信息
    overall_rps = total_requests / total_time
    successful_rps = successful_requests / total_time
    
    print("\n" + "=" * 50)
    print("性能测试结果:")
    print("=" * 50)
    print(f"总请求数: {total_requests}")
    print(f"成功请求: {successful_requests}")
    print(f"失败请求: {failed_requests}")
    print(f"成功率: {(successful_requests/total_requests)*100:.2f}%")
    print(f"总耗时: {total_time:.2f} 秒")
    print(f"总体RPS: {overall_rps:.2f} 请求/秒")
    print(f"成功RPS: {successful_rps:.2f} 请求/秒")
    
    if response_times:
        print(f"\n响应时间统计:")
        print(f"平均响应时间: {statistics.mean(response_times)*1000:.2f} ms")
        print(f"最小响应时间: {min(response_times)*1000:.2f} ms")
        print(f"最大响应时间: {max(response_times)*1000:.2f} ms")
        print(f"响应时间中位数: {statistics.median(response_times)*1000:.2f} ms")
        if len(response_times) > 1:
            print(f"响应时间标准差: {statistics.stdev(response_times)*1000:.2f} ms")
    
    return overall_rps


def main():
    print("ONVIF 摄像头快照性能测试")
    
    # 获取快照URI
    uri = get_snapshot_uri()
    if not uri:
        print("无法获取快照URI，退出测试")
        return
    
    print(f"快照URI获取成功: {uri}")
    
    # 先测试单次请求
    print("\n测试单次请求...")
    try:
        r = requests.get(uri, auth=HTTPDigestAuth(USER, PASS), timeout=5)
        r.raise_for_status()
        print(f"单次请求成功，响应大小: {len(r.content)} 字节")
    except Exception as e:
        print(f"单次请求失败: {e}")
        return
    
    total_requests = 100
    print(f'\n开始性能测试，{total_requests} 次请求')
    performance_test(uri, total_requests)


if __name__ == "__main__":
    main()
