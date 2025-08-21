"""
保存与清理工具模块
"""
import logging
import os
import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, TYPE_CHECKING
import cv2
from django.utils import timezone

from core.models import OssObject
if TYPE_CHECKING:
    from .frame import DecodedFrame

logger = logging.getLogger(__name__)


STORAGE_DIR = Path("/data/big-particle-data/storage/")
OSS_DIR = STORAGE_DIR / "oss"
ORIGINAL_DIR = OSS_DIR / "original_frames"
RENDERED_DIR = OSS_DIR / "rendered_frames"
SAVED_FRAMES_DIR = STORAGE_DIR / "saved_frames"
SAFE_FREE_SPACE_GB = 400  # 安全剩余空间阈值（GB）


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
            file_path=str(file_path.relative_to(OSS_DIR)),
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
            file_path=str(file_path.relative_to(OSS_DIR)),
            file_name=file_name,
            content_type=content_type
        )

        return oss_object.id
    except Exception as e:
        logger.error(f"保存渲染帧异常: {e}")
        return None


def _get_free_space_gb(path: Path) -> float:
    """获取指定路径的剩余磁盘空间（GB）"""
    try:
        _, _, free = shutil.disk_usage(str(path))
        return free / (1024 ** 3)
    except Exception as e:
        logger.error(f"获取磁盘空间失败: {e}")
        return float('inf')


def _list_saved_frame_dirs_older_than(cutoff_dt: datetime):
    """列出所有早于 cutoff_dt 的保存帧目录（按最旧优先排序）"""
    result = []
    if not SAVED_FRAMES_DIR.exists():
        return result
    try:
        for stream_dir_name in os.listdir(SAVED_FRAMES_DIR):
            stream_dir_path = SAVED_FRAMES_DIR / stream_dir_name
            if not stream_dir_path.is_dir():
                continue
            for time_dir_name in os.listdir(stream_dir_path):
                time_dir_path = stream_dir_path / time_dir_name
                if not time_dir_path.is_dir():
                    continue
                try:
                    mtime = os.path.getmtime(time_dir_path)
                    if datetime.fromtimestamp(mtime) < cutoff_dt:
                        result.append((mtime, time_dir_path))
                except Exception:
                    continue
    except Exception as e:
        logger.error(f"扫描保存帧目录失败: {e}")
    # 按修改时间从旧到新排序
    result.sort(key=lambda x: x[0])
    return [p for _, p in result]


def _cleanup_old_oss_objects(max_count: int = 1000) -> int:
    """清理最旧的未标记删除的 OSS 记录，删除本地文件并设置 deleted_at，返回处理数量"""
    try:
        qs = OssObject.objects.filter(deleted_at__isnull=True).order_by('created_at')[:max_count]
        now = timezone.now()
        processed = 0
        for obj in qs:
            try:
                file_path = OSS_DIR / obj.file_path
                # 尝试删除文件
                try:
                    if file_path.exists():
                        file_path.unlink()
                except Exception as remove_err:
                    logger.error(f"删除文件失败 {file_path}: {remove_err}")

                # 标记记录为已删除
                obj.deleted_at = now
                obj.save(update_fields=['deleted_at'])
                processed += 1
            except Exception as e:
                logger.error(f"处理 OSS 记录失败 id={obj.id}: {e}")
                continue
        if processed:
            logger.info(f"已清理最旧的 OSS 记录 {processed}/{max_count} 条")
        return processed
    except Exception as e:
        logger.error(f"查询或清理 OSS 记录失败: {e}")
        return 0


def _cleanup_storage_if_low_space():
    """清理逻辑：
    - 若空间不足首先逐个删除最旧的保存帧目录，至少保留最近3天，每删除一次重新判断空间
    - 若仍不足，则按批删除最旧的未删除OSS记录，每批1000条，删除后再次判断空间
    - 直到空间充足或无可删除项为止
    """
    free_gb = _get_free_space_gb(STORAGE_DIR)
    if free_gb >= SAFE_FREE_SPACE_GB:
        logger.info(f"磁盘空间充足: {free_gb:.1f}GB >= {SAFE_FREE_SPACE_GB}GB")
        return

    logger.warning(f"磁盘空间不足: {free_gb:.1f}GB < {SAFE_FREE_SPACE_GB}GB，开始清理...")

    cutoff = datetime.now() - timedelta(days=3)
    removed_dirs = 0
    cleaned_oss_total = 0

    # 1) 一次性获取所有早于 cutoff 的目录，按最旧优先逐个删除，每删一次重检空间
    older_dirs = _list_saved_frame_dirs_older_than(cutoff)
    for dir_path in older_dirs:
        if free_gb >= SAFE_FREE_SPACE_GB:
            break
        try:
            shutil.rmtree(dir_path)
            removed_dirs += 1
            logger.info(f"已删除保存帧目录: {dir_path}")
        except Exception as e:
            logger.error(f"删除目录失败 {dir_path}: {e}")
            continue
        free_gb = _get_free_space_gb(STORAGE_DIR)

    # 2) 若仍不足，则按批次删除最旧的 OSS 记录，每批1000条
    while free_gb < SAFE_FREE_SPACE_GB:
        cleaned = _cleanup_old_oss_objects(max_count=1000)
        cleaned_oss_total += cleaned
        if cleaned <= 0:
            break
        free_gb = _get_free_space_gb(STORAGE_DIR)

    logger.info(
        f"清理完成：剩余空间 {free_gb:.1f}GB，删除保存帧目录 {removed_dirs} 个；清理 OSS 记录 {cleaned_oss_total} 条"
    )


# 全局清理线程
cleanup_thread = None
cleanup_running = False
cleanup_stop_event = threading.Event()


def _cleanup_loop():
    """清理线程主循环：每30秒调用一次统一清理逻辑"""
    global cleanup_running, cleanup_stop_event
    while cleanup_running:
        try:
            _cleanup_storage_if_low_space()
            cleanup_stop_event.wait(timeout=30)
        except:
            logger.exception(f"清理线程异常")
            cleanup_stop_event.wait(timeout=30)
    logger.info("清理线程退出")


def start_cleanup_thread():
    """启动清理线程"""
    logger.info("启动清理线程")
    global cleanup_thread, cleanup_running
    if cleanup_thread and cleanup_thread.is_alive():
        logger.info("清理线程已在运行")
        return
    cleanup_running = True
    cleanup_stop_event.clear()
    cleanup_thread = threading.Thread(target=_cleanup_loop, name="frame-cleanup")
    cleanup_thread.start()
    logger.info("清理线程已启动")


def stop_cleanup_thread():
    """停止清理线程"""
    logger.info("停止清理线程")
    global cleanup_thread, cleanup_running, cleanup_stop_event
    cleanup_running = False
    cleanup_stop_event.set()
    if cleanup_thread and cleanup_thread.is_alive():
        cleanup_thread.join(timeout=5.0)
        if cleanup_thread.is_alive():
            logger.warning("清理线程未能在5秒内正常结束")
        else:
            logger.info("清理线程已停止")
