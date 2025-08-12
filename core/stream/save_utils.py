"""
保存工具模块
"""
import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING
import cv2

from core.models import OssObject
if TYPE_CHECKING:
    from .frame import DecodedFrame

logger = logging.getLogger(__name__)


BASE_DIR = Path("/data/big-particle-data/storage/oss/")
ORIGINAL_DIR = BASE_DIR / "original_frames"
RENDERED_DIR = BASE_DIR / "rendered_frames"


def save_original_frame(frame: 'DecodedFrame') -> Optional[int]:
    """
    保存原始帧到本地并创建OSS对象记录
    """
    try:
        file_name = f"stream_{frame.stream_id}_{frame.timestamp}.png"
        file_path = ORIGINAL_DIR / file_name

        # 确保保存目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        success = cv2.imwrite(str(file_path), frame.ocv_image)
        if not success:
            logger.error(f"保存原始帧失败: {file_path}")
            return None
        
        oss_object = OssObject.objects.create(
            file_path=str(file_path.relative_to(BASE_DIR)),
            file_name=file_name,
            content_type="image/png"
        )
        
        return oss_object.id
    except Exception as e:
        logger.error(f"保存帧异常: {e}")
        return None


def save_rendered_image(image, file_name: str) -> Optional[int]:
    """
    保存渲染帧到本地并创建OSS对象记录
    """
    try:
        file_path = RENDERED_DIR / file_name

        # 确保保存目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)

        success = cv2.imwrite(str(file_path), image)
        if not success:
            logger.error(f"保存渲染帧失败: {file_path}")
            return None
        
        content_type = "image/jpeg" if file_name.endswith(".jpg") else "image/png"
        oss_object = OssObject.objects.create(
            file_path=str(file_path.relative_to(BASE_DIR)),
            file_name=file_name,
            content_type=content_type
        )

        return oss_object.id
    except Exception as e:
        logger.error(f"保存渲染帧异常: {e}")
        return None
