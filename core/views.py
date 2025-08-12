import logging
import cv2
from django.contrib.auth.models import User, Group
from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from .models import VideoStream, AlgoBigParticleRecord
from .serializers import UserSerializer, GroupSerializer, VideoStreamSerializer, BigParticleRecordQuerySerializer, BigParticleRecordResponseSerializer
from .stream.video_processor import create_processor, remove_processor, get_processor

logger = logging.getLogger(__name__)


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
                logger.error(f"自动打开视频流失败: {e}")
    
    def perform_update(self, serializer):
        """更新时处理启用/禁用状态变化和配置热更新"""
        old_enabled = serializer.instance.enabled
        new_enabled = serializer.validated_data.get('enabled', old_enabled)
        
        # 检查是否需要重启流（配置变化）
        restart_required = getattr(serializer.instance, '_restart_required', False)
        save_frames_changed = getattr(serializer.instance, '_save_frames_changed', False)
        
        # TODO 考虑多线程并发
        existing_processor = get_processor(serializer.instance.id)
        
        # 先保存客户端数据
        video_stream = serializer.save()
        
        # 处理不同的更新场景
        if old_enabled and not new_enabled:
            logger.info(f"禁用视频流: {video_stream.id}")
            # 从启用→禁用：关闭视频流
            if existing_processor:
                try:
                    remove_processor(video_stream.id)
                except Exception as e:
                    logger.error(f"禁用视频流失败: {e}")
            else:
                logger.info(f"视频流处理器不存在: {video_stream.id}")
            # 更新状态为未启用
            video_stream.status = VideoStream.Status.DISABLED
            video_stream.status_message = ""
            video_stream.save(update_fields=['status', 'status_message'])
        elif not old_enabled and new_enabled:
            logger.info(f"启用视频流: {video_stream.id}")
            # 从禁用→启用：启动处理器
            try:
                create_processor(video_stream)
                video_stream.status = VideoStream.Status.NORMAL
                video_stream.status_message = ""
                video_stream.save(update_fields=['status', 'status_message'])
            except Exception as e:
                video_stream.status = VideoStream.Status.ABNORMAL
                video_stream.status_message = f"启动失败: {str(e)}"
                video_stream.save(update_fields=['status', 'status_message'])
                logger.error(f"启用视频流失败: {e}")
        
        # 处理其他场景（不需要更新数据库状态）
        # 禁用->启用会创建新的流，因此只需要在启动状态下重启流
        if old_enabled and new_enabled:
            if restart_required and existing_processor:
                # 启用状态下配置变化：重启视频流（自动包含新的 save_frames 设置）
                try:
                    logger.info(f"配置变化，重启视频流: {video_stream.id}")
                    remove_processor(video_stream.id)
                    create_processor(video_stream)
                    logger.info(f"视频流重启成功: {video_stream.id}")
                except Exception as e:
                    logger.error(f"重启视频流失败: {e}")
            
            # 处理 save_frames 变化（仅在不需要重启时）
            elif save_frames_changed and existing_processor:
                try:
                    save_frames_new = serializer.validated_data.get('save_frames', serializer.instance.save_frames)
                    logger.info(f"更新保存帧设置: {video_stream.id} -> {save_frames_new}")
                    existing_processor.video_stream.save_frames = save_frames_new
                    if save_frames_new:
                        existing_processor.start_save_thread()
                    else:
                        existing_processor.stop_save_thread()
                except Exception as e:
                    logger.error(f"更新保存设置失败: {e}")
        
        # 清理临时标记
        if hasattr(video_stream, '_restart_required'):
            delattr(video_stream, '_restart_required')
        if hasattr(video_stream, '_save_frames_changed'):
            delattr(video_stream, '_save_frames_changed')
    
    def perform_destroy(self, instance):
        """删除时关闭视频流"""
        try:
            logger.info(f"删除视频流: {instance.id}")
            remove_processor(instance.id)
        except Exception as e:
            logger.error(f"删除时关闭视频流失败: {e}")
        
        # 执行实际删除
        instance.delete()
    
    @action(detail=True, methods=['get'])
    def latest_frame(self, request, pk=None):
        """获取视频流的最新帧图像"""
        try:
            video_stream = self.get_object()
            
            # 获取处理器
            processor = get_processor(video_stream.id)
            if not processor:
                return Response(
                    {"error": "视频流处理器未运行"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # 获取最新帧
            frame = processor.get_latest_frame()
            if frame is None:
                return Response(
                    {"error": "暂无可用帧"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # 使用opencv将帧编码为JPG
            success, buffer = cv2.imencode('.jpg', frame.ocv_image)
            if not success:
                return Response(
                    {"error": "图像编码失败"}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # 返回JPG字节流
            response = HttpResponse(buffer.tobytes(), content_type='image/jpeg')
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response
            
        except Exception as e:
            logger.error(f"获取最新帧失败: {e}")
            return Response(
                {"error": f"获取最新帧失败: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BigParticleRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """大颗粒记录查询视图集"""
    
    queryset = AlgoBigParticleRecord.objects.all()
    serializer_class = BigParticleRecordResponseSerializer
    
    def get_queryset(self):
        """根据查询参数过滤记录"""
        # 获取查询参数
        query_serializer = BigParticleRecordQuerySerializer(data=self.request.query_params)
        if not query_serializer.is_valid():
            raise ValidationError(query_serializer.errors)
        
        validated_data = query_serializer.validated_data
        queryset = self.queryset
        
        # 根据流ID过滤
        stream_ids = validated_data.get('stream_ids')
        if stream_ids:
            queryset = queryset.filter(stream_id__in=stream_ids)
        
        # 根据流名称模糊匹配过滤
        stream_name = validated_data.get('stream_name')
        if stream_name:
            queryset = queryset.filter(stream_name__icontains=stream_name)
        
        # 根据时间范围过滤
        start_time = validated_data.get('start_time')
        if start_time:
            queryset = queryset.filter(detected_at__gte=start_time)
            
        end_time = validated_data.get('end_time')
        if end_time:
            queryset = queryset.filter(detected_at__lte=end_time)
        
        # 根据粒径范围过滤（基于最大粒径）
        min_max_size = validated_data.get('min_max_size')
        if min_max_size is not None:
            queryset = queryset.filter(max_size__gte=min_max_size)
            
        max_max_size = validated_data.get('max_max_size')
        if max_max_size is not None:
            queryset = queryset.filter(max_size__lte=max_max_size)
        
        return queryset
