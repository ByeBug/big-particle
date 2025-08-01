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
        existing_processor = get_processor(video_stream.id)
        
        # 处理不同的更新场景
        if old_enabled and not new_enabled:
            # 从启用→禁用：关闭视频流
            if existing_processor:
                try:
                    remove_processor(video_stream.id)
                    print(f"禁用视频流: {video_stream.id}")
                except Exception as e:
                    print(f"禁用视频流失败: {e}")
                    
        elif not old_enabled and new_enabled:
            # 从禁用→启用：打开视频流
            try:
                create_processor(video_stream)
                print(f"启用视频流: {video_stream.id}")
            except Exception as e:
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
        
        # 清理临时标记
        if hasattr(video_stream, '_restart_required'):
            delattr(video_stream, '_restart_required')
    
    def perform_destroy(self, instance):
        """删除时关闭视频流"""
        try:
            remove_processor(instance.id)
            print(f"删除视频流，已关闭处理器: {instance.id}")
        except Exception as e:
            print(f"删除时关闭视频流失败: {e}")
        
        # 执行实际删除
        instance.delete()
    
    @action(detail=True, methods=['post'])
    def open(self, request, pk=None):
        video_stream = self.get_object()
        
        # 检查是否已经打开
        existing_processor = get_processor(video_stream.id)
        if existing_processor:
            return Response({
                'status': 'already_opened', 
                'id': video_stream.id,
                'message': '视频流已经在运行中'
            })
        
        # 创建并启动处理器
        try:
            processor = create_processor(video_stream)
            return Response({
                'status': 'opened', 
                'id': video_stream.id,
                'message': '视频流已成功启动'
            })
        except Exception as e:
            return Response({
                'status': 'error',
                'id': video_stream.id,
                'message': f'启动失败: {str(e)}'
            }, status=500)
    
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        video_stream = self.get_object()
        
        # 检查处理器是否存在
        existing_processor = get_processor(video_stream.id)
        if not existing_processor:
            return Response({
                'status': 'already_closed',
                'id': video_stream.id,
                'message': '视频流未在运行'
            })
        
        # 停止并移除处理器
        try:
            remove_processor(video_stream.id)
            return Response({
                'status': 'closed',
                'id': video_stream.id,
                'message': '视频流已停止'
            })
        except Exception as e:
            return Response({
                'status': 'error',
                'id': video_stream.id,
                'message': f'停止失败: {str(e)}'
            }, status=500)
