import logging
import cv2
from django.contrib.auth.models import User, Group
from django.db import connection
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from datetime import timedelta

from .models import VideoStream, AlgoBigParticleRecord, SystemConfig
from .serializers import (
    UserSerializer, GroupSerializer, VideoStreamSerializer,
    BigParticleRecordQuerySerializer, BigParticleRecordResponseSerializer,
    BigParticleStatsQuerySerializer, SystemConfigSerializer
)
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

class BigParticleStatsAPIView(APIView):
    """大颗粒统计API视图"""
    
    def _get_size_levels(self):
        """从系统配置获取粒径等级"""

        big_particle_config = SystemConfig.objects.filter(
            config_type='algorithm',
            name='big_particle',
            is_active=True
        ).first()
        
        alarm_threshold = big_particle_config.config_data['alarm_threshold']
        # 从 alarm_threshold 中获取粒径等级，并排序
        size_levels = sorted([threshold['size_level'] for threshold in alarm_threshold])
        return size_levels
    
    def get(self, request):
        """获取大颗粒统计数据"""
        # 验证查询参数
        query_serializer = BigParticleStatsQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            raise ValidationError(query_serializer.errors)
        
        stream_ids = query_serializer.validated_data['stream_ids']
        
        # 获取动态粒径等级
        size_levels = self._get_size_levels()
        
        # 计算时间边界
        now = timezone.now()
        thirty_seconds_ago = now - timedelta(seconds=30)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # 构建SQL参数
        placeholders = ','.join(['%s'] * len(stream_ids))
        
        # 根据等级动态构建CASE WHEN子句
        case_when_clauses = []
        for i, level in enumerate(size_levels):
            if i == len(size_levels) - 1:
                # 最后一个等级：>=该等级
                case_when_clauses.append(f"COUNT(CASE WHEN max_size >= {level} THEN 1 END) AS count_{level}")
            else:
                # 中间等级：>=当前等级且<下一等级
                next_level = size_levels[i + 1]
                case_when_clauses.append(f"COUNT(CASE WHEN max_size >= {level} AND max_size < {next_level} THEN 1 END) AS count_{level}")
        
        case_when_sql = ",\n                    ".join(case_when_clauses)
        
        # 执行两个 SQL 查询
        with connection.cursor() as cursor:
            # 查询1: 30秒内统计
            recent_sql = f"""
                SELECT 
                    stream_id,
                    {case_when_sql}
                FROM algo_big_particle_record
                WHERE detected_at >= %s AND stream_id IN ({placeholders})
                GROUP BY stream_id
            """
            
            cursor.execute(recent_sql, [thirty_seconds_ago] + stream_ids)
            recent_rows = cursor.fetchall()
            
            # 查询2: 当天统计
            today_sql = f"""
                SELECT 
                    stream_id,
                    {case_when_sql}
                FROM algo_big_particle_record
                WHERE detected_at >= %s AND detected_at <= %s AND stream_id IN ({placeholders})
                GROUP BY stream_id
            """
            
            cursor.execute(today_sql, [today_start, today_end] + stream_ids)
            today_rows = cursor.fetchall()
        
        # 构建结果字典
        recent_results = {}
        for row in recent_rows:
            stream_id = row[0]
            level_counts = {}
            for i, level in enumerate(size_levels):
                level_counts[str(level)] = row[i + 1]  # row[0]是stream_id，从row[1]开始是统计数据
            recent_results[stream_id] = level_counts
        
        today_results = {}
        for row in today_rows:
            stream_id = row[0]
            level_counts = {}
            for i, level in enumerate(size_levels):
                level_counts[str(level)] = row[i + 1]
            today_results[stream_id] = level_counts
        
        # 构建默认的0值字典
        default_counts = {str(level): 0 for level in size_levels}
        
        # 构建响应数据
        results = []
        for stream_id in stream_ids:
            # 获取该流的统计数据
            recent_data = recent_results.get(stream_id, default_counts.copy())
            today_data = today_results.get(stream_id, default_counts.copy())
            
            # 构建该流的统计结果
            stream_stats = {
                "stream_id": stream_id,
                "stats": [
                    {
                        "range": "recent_30s",
                        "values": [{"level": level, "count": recent_data[str(level)]} for level in size_levels]
                    },
                    {
                        "range": "today", 
                        "values": [{"level": level, "count": today_data[str(level)]} for level in size_levels]
                    }
                ]
            }
            results.append(stream_stats)
        
        return Response({"results": results})


class SystemConfigViewSet(viewsets.ModelViewSet):
    """系统配置视图集"""
    
    queryset = SystemConfig.objects.all()
    serializer_class = SystemConfigSerializer
    
    def get_queryset(self):
        """根据查询参数过滤配置"""
        queryset = self.queryset
        
        # 根据配置类型过滤
        config_type = self.request.query_params.get('config_type')
        if config_type:
            queryset = queryset.filter(config_type=config_type)
        
        # 根据名称过滤
        name = self.request.query_params.get('name')
        if name:
            queryset = queryset.filter(name=name)
        
        # 根据是否启用过滤
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            if is_active.lower() in ['true', '1']:
                queryset = queryset.filter(is_active=True)
            elif is_active.lower() in ['false', '0']:
                queryset = queryset.filter(is_active=False)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def types(self, request):
        """获取所有配置类型"""
        types = SystemConfig.objects.values_list('config_type', flat=True).distinct()
        return Response(list(types))
