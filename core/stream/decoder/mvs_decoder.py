"""
MVS 相机解码器
"""

import sys
import time
import threading
import cv2
import numpy as np
from typing import Optional
from ctypes import string_at

from .base import BaseDecoder
from ..frame import DecodedFrame

# 尝试导入 MVS SDK
try:
    mvs_path = "/opt/MVS/Samples/64/Python/MvImport"
    if mvs_path not in sys.path:
        sys.path.append(mvs_path)
    
    from MvCameraControl_class import *
    HAS_MVS_SDK = True
except ImportError as e:
    HAS_MVS_SDK = False
    _MVS_IMPORT_ERROR = e


class MVSDecoder(BaseDecoder):
    """MVS 相机解码器
    
    用于从 MVS 相机获取图像数据
    """
    
    # 类变量：SDK 初始化状态和实例集合（线程安全）
    _sdk_initialized = False
    _active_instances = set()  # 活跃实例集合
    _class_lock = threading.Lock()  # 类级别的锁，保护类变量
    
    def __init__(self, video_stream):
        super().__init__(video_stream)
        self._camera: MvCamera = None
        
        # 检查 MVS SDK 是否可用
        if not HAS_MVS_SDK:
            print("MVS SDK 不可用，请安装 MVS 相机驱动")
            raise _MVS_IMPORT_ERROR
        
        # 线程安全的 SDK 初始化和实例注册
        with MVSDecoder._class_lock:
            # 初始化 MVS SDK（只初始化一次）
            if not MVSDecoder._sdk_initialized:
                MVSDecoder._initialize_sdk()
            
            # 注册当前实例
            MVSDecoder._active_instances.add(self)
    
    @classmethod
    def _initialize_sdk(cls):
        """
        初始化 MVS SDK（类方法，只执行一次）
        
        执行 SDK 的全局初始化设置，如参数配置等
        """
        try:
            MvCamera.MV_CC_Initialize()
            print("MVS SDK 初始化成功")
            cls._sdk_initialized = True
        except Exception as e:
            print(f"MVS SDK 初始化失败: {e}")
            cls._sdk_initialized = False
            raise e
    
    @classmethod
    def is_sdk_available(cls) -> bool:
        """
        检查 MVS SDK 是否可用
        
        Returns:
            bool: SDK 是否已成功导入
        """
        return HAS_MVS_SDK
    
    @classmethod
    def is_sdk_initialized(cls) -> bool:
        """
        检查 MVS SDK 是否已初始化（线程安全）
        
        Returns:
            bool: SDK 是否已初始化
        """
        with cls._class_lock:
            return cls._sdk_initialized
    
    @classmethod
    def _finalize_sdk(cls):
        """
        清理 MVS SDK（类方法，在没有活跃实例时执行）
        
        清理 SDK 的全局资源
        """
        try:
            if cls._sdk_initialized:
                MvCamera.MV_CC_Finalize()
                print("MVS SDK 清理完成")
                cls._sdk_initialized = False
        except Exception as e:
            print(f"MVS SDK 清理失败: {e}")
            cls._sdk_initialized = False
    
    @classmethod
    def get_active_instances_count(cls) -> int:
        """
        获取活跃实例数量（线程安全）
        
        Returns:
            int: 活跃实例数量
        """
        with cls._class_lock:
            return len(cls._active_instances)
    
    def open(self) -> bool:
        """
        打开 MVS 相机连接
        
        Returns:
            bool: 是否成功打开
        """
        try:
            if self._is_opened:
                return True
            
            # 枚举设备
            device_list = MV_CC_DEVICE_INFO_LIST()
            tlayerType = (MV_GIGE_DEVICE | MV_USB_DEVICE | MV_GENTL_CAMERALINK_DEVICE
                | MV_GENTL_CXP_DEVICE | MV_GENTL_XOF_DEVICE)
            
            ret = MvCamera.MV_CC_EnumDevices(tlayerType, device_list)
            if ret != 0:
                print(f"枚举设备失败，错误码: {ret:#X}")
                return False
            
            # 查找指定 IP 的设备
            target_ip = self.video_stream.address
            device_index = None
            device_info = None
            
            for i in range(device_list.nDeviceNum):
                mvcc_dev_info = cast(device_list.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents
                if mvcc_dev_info.nTLayerType == MV_GIGE_DEVICE or mvcc_dev_info.nTLayerType == MV_GENTL_GIGE_DEVICE:
                    # print(f"\ngige device: [{i}]")

                    device_ip = ".".join([
                        str((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0xff000000) >> 24),
                        str((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x00ff0000) >> 16),
                        str((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x0000ff00) >> 8),
                        str(mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x000000ff)
                    ])
                    # print(f'ip: {device_ip}')

                    # 设备型号
                    strModeName = ""
                    for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chModelName:
                        if per == 0:
                            break
                        strModeName = strModeName + chr(per)
                    # print(f"mode name: {strModeName}")

                    # 序列号
                    strSerialNumber = ""
                    for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chSerialNumber:
                        if per == 0:
                            break
                        strSerialNumber = strSerialNumber + chr(per)
                    # print(f"serial number: {strSerialNumber}")
                    
                    if device_ip == target_ip:
                        device_index = i
                        device_info = mvcc_dev_info
                        break
            
            if device_index is None:
                print(f"未找到 IP 为 {target_ip} 的 MVS 设备")
                return False
            
            # 创建相机实例
            self._camera = MvCamera()

            # 创建句柄
            ret = self._camera.MV_CC_CreateHandle(device_info)
            if ret != 0:
                print(f"创建设备句柄失败，错误码: {ret:#X}")
                return False
            
            # 打开设备
            ret = self._camera.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
            if ret != 0:
                print(f"打开设备失败，错误码: {ret:#X}")
                self._camera.MV_CC_DestroyHandle()
                return False
            
            # 探测网络最佳包大小
            if device_info.nTLayerType == MV_GIGE_DEVICE or device_info.nTLayerType == MV_GENTL_GIGE_DEVICE:
                packet_size = self._camera.MV_CC_GetOptimalPacketSize()
                if packet_size > 0:
                    ret = self._camera.MV_CC_SetIntValue("GevSCPSPacketSize", packet_size)
                    if ret != 0:
                        print(f"警告：设置包大小失败，错误码: {ret}")
            
            # 设置触发模式为 off
            ret = self._camera.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
            if ret != 0:
                print(f"设置触发模式为 off 失败，错误码: {ret:#X}")
                return False
            
            # 设置采集帧率
            ret = self._camera.MV_CC_SetFloatValue("AcquisitionFrameRate", float(self.fps))
            if ret != 0:
                print(f"设置采集帧率失败，错误码: {ret:#X}")
                return False
            
            # 开始取流
            ret = self._camera.MV_CC_StartGrabbing()
            if ret != 0:
                print(f"开始取流失败，错误码: {ret:#X}")
                self._camera.MV_CC_CloseDevice()
                self._camera.MV_CC_DestroyHandle()
                return False
            
            # 创建图像缓存
            self._stOutFrame = MV_FRAME_OUT()
            memset(byref(self._stOutFrame), 0, sizeof(self._stOutFrame))

            # 读取第一帧图像获取尺寸信息
            first_frame = self.read_frame()
            if first_frame is None:
                print("无法获取第一帧图像")
                self._camera.MV_CC_StopGrabbing()
                self._camera.MV_CC_CloseDevice()
                self._camera.MV_CC_DestroyHandle()
                return False
            
            # 更新实例属性
            self.width = first_frame.width
            self.height = first_frame.height

            self._is_opened = True
            self.reset_stats()
            print(f"成功打开 MVS 相机: {target_ip}")
            return True
            
        except Exception as e:
            print(f"打开 MVS 相机失败: {e}")
            return False
    
    def close(self):
        """
        关闭 MVS 相机连接
        """
        try:
            if self._camera and self._is_opened:
                # 停止取流
                self._camera.MV_CC_StopGrabbing()
                
                # 关闭设备
                self._camera.MV_CC_CloseDevice()
                
                # 销毁句柄
                self._camera.MV_CC_DestroyHandle()
                
                print(f"成功关闭 MVS 相机: {self.video_stream.address}")
            
            self._camera = None
            self._is_opened = False
            
        except Exception as e:
            print(f"关闭 MVS 相机失败: {e}")
        finally:
            # 线程安全的实例管理和 SDK 清理
            with MVSDecoder._class_lock:
                # 移除当前实例
                MVSDecoder._active_instances.discard(self)
                
                # 如果没有活跃实例了，清理 SDK
                if len(MVSDecoder._active_instances) == 0:
                    MVSDecoder._finalize_sdk()
    
    
    def read_frame(self) -> Optional[DecodedFrame]:
        """
        从 MVS 相机读取一帧图像
        
        Returns:
            Optional[DecodedFrame]: 解码帧对象，失败返回 None
        """
        if not self._camera:
            return None
        
        try:
            # 获取一帧数据
            ret = self._camera.MV_CC_GetImageBuffer(self._stOutFrame, 1000)
            if ret == 0 and self._stOutFrame.pBufAddr is not None:
                # 转换为 OpenCV 图像
                opencv_image = self._convert_to_opencv_image(self._stOutFrame)
                if opencv_image is not None:
                    # 返回 DecodedFrame 对象
                    return DecodedFrame(
                        ocv_image=opencv_image,
                        width=self._stOutFrame.stFrameInfo.nWidth,
                        height=self._stOutFrame.stFrameInfo.nHeight,
                        frame_number=self._stOutFrame.stFrameInfo.nFrameNum,
                        timestamp=time.time(),
                        stream_id=self.video_stream.id
                    )
                else:
                    # 转换失败，返回 None
                    return None
            else:
                print(f"获取图像失败，错误码: {ret:#X}")
                return None
                
        except Exception as e:
            print(f"读取 MVS 相机帧失败: {e}")
            return None
        finally:
            self._camera.MV_CC_FreeImageBuffer(self._stOutFrame)
    
    def is_opened(self) -> bool:
        """
        检查 MVS 相机是否已打开
        
        Returns:
            bool: 是否已打开
        """
        return self._is_opened and self._camera is not None
    
    def _convert_to_opencv_image(self, stOutFrame) -> Optional[np.ndarray]:
        """
        将 MVS 相机的原始帧数据转换为 OpenCV 图像格式
        
        Args:
            stOutFrame: MVS SDK 的 MV_FRAME_OUT 结构体
            
        Returns:
            np.ndarray: OpenCV 图像，失败返回 None
        """
        try:
            if not stOutFrame or not stOutFrame.pBufAddr:
                return None
            
            # 从 stOutFrame 获取图像信息
            width = stOutFrame.stFrameInfo.nWidth
            height = stOutFrame.stFrameInfo.nHeight
            pixel_format = stOutFrame.stFrameInfo.enPixelType
            frame_len = stOutFrame.stFrameInfo.nFrameLen
            
            # print(f"图像参数: width={width}, height={height}, format={pixel_format}, len={frame_len}")
            
            if width <= 0 or height <= 0 or frame_len <= 0:
                print(f"无效的图像参数: width={width}, height={height}, frame_len={frame_len}")
                return None
            
            # 获取原始图像数据
            # pBufAddr 是 POINTER(c_ubyte)，直接使用指针内容
            raw_data = string_at(stOutFrame.pBufAddr, frame_len)
            
            # 根据像素格式转换图像
            opencv_image = None
            
            # Mono8 格式
            if pixel_format == PixelType_Gvsp_Mono8:
                # 单通道灰度图 - 进行内存拷贝
                image_array = np.frombuffer(raw_data, dtype=np.uint8).copy()
                opencv_image = image_array.reshape((height, width))
            
            # BGR8 格式
            elif pixel_format == PixelType_Gvsp_BGR8_Packed:
                # 三通道彩色图 (BGR) - 进行内存拷贝
                image_array = np.frombuffer(raw_data, dtype=np.uint8).copy()
                opencv_image = image_array.reshape((height, width, 3))
            
            # RGB8 格式转 BGR
            elif pixel_format == PixelType_Gvsp_RGB8_Packed:
                # 三通道彩色图 (RGB -> BGR) - 进行内存拷贝
                image_array = np.frombuffer(raw_data, dtype=np.uint8).copy()
                rgb_image = image_array.reshape((height, width, 3))
                opencv_image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
            
            # YUV422 格式
            elif pixel_format == PixelType_Gvsp_YUV422_Packed:
                # YUV422 转 BGR - 进行内存拷贝
                image_array = np.frombuffer(raw_data, dtype=np.uint8).copy()
                yuv_image = image_array.reshape((height, width * 2))
                opencv_image = cv2.cvtColor(yuv_image, cv2.COLOR_YUV2BGR_UYVY)
            
            else:
                print(f"不支持的像素格式: {pixel_format}")
            
            # 直接返回 OpenCV 图像
            return opencv_image
            
        except Exception as e:
            print(f"转换 OpenCV 图像失败: {e}")
            return None
