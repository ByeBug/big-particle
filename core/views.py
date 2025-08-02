from django.contrib.auth.models import User, Group
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import VideoStream
from .serializers import UserSerializer, GroupSerializer, VideoStreamSerializer
from .stream.video_processor import create_processor, remove_processor, get_processor


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer


class VideoStreamViewSet(viewsets.ModelViewSet):
    queryset = VideoStream.objects.all()
    serializer_class = VideoStreamSerializer
    
    def perform_create(self, serializer):
        """创建后如果启用则自动打开视频流"""
        video_stream = serializer.save()
        
        # 如果创建时启用，自动打开视频流
        if video_stream.enabled:
            try:
                create_processor(video_stream)
            except Exception as e:
                print(f"自动打开视频流失败: {e}")
    
    def perform_update(self, serializer):
        """更新时处理启用/禁用状态变化和配置热更新"""
        old_enabled = self.get_object().enabled
        video_stream = serializer.save()
        new_enabled = video_stream.enabled
        
        # 检查是否需要重启流（配置变化）
        restart_required = getattr(video_stream, '_restart_required', False)
        save_frames_changed = getattr(video_stream, '_save_frames_changed', False)
        existing_processor = get_processor(video_stream.id)
        
        # 处理不同的更新场景
        if old_enabled and not new_enabled:
            # 从启用→禁用：关闭视频流，设置状态为未启用
            if existing_processor:
                try:
                    remove_processor(video_stream.id)
                    print(f"禁用视频流: {video_stream.id}")
                except Exception as e:
                    print(f"禁用视频流失败: {e}")
            # 更新状态为未启用
            video_stream.status = VideoStream.Status.DISABLED
            video_stream.status_message = ""
            video_stream.save(update_fields=['status', 'status_message'])
                    
        elif not old_enabled and new_enabled:
            # 从禁用→启用：打开视频流，设置状态为正常
            try:
                create_processor(video_stream)
                # 启动成功，设置状态为正常
                video_stream.status = VideoStream.Status.NORMAL
                video_stream.status_message = ""
                video_stream.save(update_fields=['status', 'status_message'])
                print(f"启用视频流: {video_stream.id}")
            except Exception as e:
                # 启动失败，设置状态为异常
                video_stream.status = VideoStream.Status.ABNORMAL
                video_stream.status_message = f"启动失败: {str(e)}"
                video_stream.save(update_fields=['status', 'status_message'])
                print(f"启用视频流失败: {e}")
                
        elif new_enabled and restart_required and existing_processor:
            # 启用状态下配置变化：重启视频流
            try:
                print(f"配置变化，重启视频流: {video_stream.id}")
                remove_processor(video_stream.id)  # 先关闭
                create_processor(video_stream)     # 再启动
                print(f"视频流重启成功: {video_stream.id}")
            except Exception as e:
                print(f"重启视频流失败: {e}")
                # 重启失败，尝试恢复
                try:
                    create_processor(video_stream)
                    print(f"重启失败，已尝试恢复: {video_stream.id}")
                except Exception as recovery_error:
                    print(f"恢复也失败: {recovery_error}")
        
        # 处理 save_frames 变化（不需要重启整个流）
        elif new_enabled and save_frames_changed and existing_processor:
            try:
                if video_stream.save_frames:
                    # 启用保存
                    existing_processor.start_save_thread()
                else:
                    # 禁用保存
                    existing_processor.stop_save_thread()
                print(f"保存帧设置已更新: {video_stream.id} -> {video_stream.save_frames}")
            except Exception as e:
                print(f"更新保存设置失败: {e}")
        
        # 清理临时标记
        if hasattr(video_stream, '_restart_required'):
            delattr(video_stream, '_restart_required')
        if hasattr(video_stream, '_save_frames_changed'):
            delattr(video_stream, '_save_frames_changed')
    
    def perform_destroy(self, instance):
        """删除时关闭视频流"""
        try:
            remove_processor(instance.id)
            print(f"删除视频流，已关闭处理器: {instance.id}")
        except Exception as e:
            print(f"删除时关闭视频流失败: {e}")
        
        # 执行实际删除
        instance.delete()
    
