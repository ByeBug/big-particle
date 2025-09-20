import logging
import cv2
import numpy as np
from django.contrib.auth.models import User, Group
from django.db import connection, models
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from datetime import timedelta

from .models import AlgoBigParticleDetail, VideoStream, AlgoRecord, AlgoBlacklist, SystemConfig, OssObject, Alarm
from .serializers import (
    UserSerializer, GroupSerializer, VideoStreamSerializer,
    BigParticleRecordQuerySerializer, BigParticleRecordResponseSerializer,
    BigParticleStatsQuerySerializer, BigParticleHourlyStatsQuerySerializer, BigParticleDailyStatsQuerySerializer, SystemConfigSerializer,
    AlgoBlacklistSerializer, AlarmQuerySerializer, AlarmResponseSerializer
)
from .stream.video_processor import create_processor, remove_processor, get_processor
from .stream.save_utils import save_image, OSS_DIR, BLACKLIST_DIR, delete_oss_images

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
    
    queryset = AlgoRecord.objects.all()
    serializer_class = BigParticleRecordResponseSerializer
    
    def list(self, request, *args, **kwargs):
        """重写 list 方法来自定义分页逻辑"""
        # 获取查询参数
        query_serializer = BigParticleRecordQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            raise ValidationError(query_serializer.errors)
        
        validated_data = query_serializer.validated_data
        
        # 获取分页参数
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except:
            page = 1
        page_size = 30
        
        # 先从大颗粒详情表中查询符合条件的记录
        detail_queryset = AlgoBigParticleDetail.objects.all()
        
        # 根据流ID过滤
        stream_ids = validated_data.get('stream_ids')
        if stream_ids:
            detail_queryset = detail_queryset.filter(stream_id__in=stream_ids)
        
        # 根据流名称模糊匹配过滤
        stream_name = validated_data.get('stream_name')
        if stream_name:
            detail_queryset = detail_queryset.filter(stream_name__icontains=stream_name)
        
        # 根据时间范围过滤
        start_time = validated_data.get('start_time')
        if start_time:
            detail_queryset = detail_queryset.filter(detected_at__gte=start_time)
            
        end_time = validated_data.get('end_time')
        if end_time:
            detail_queryset = detail_queryset.filter(detected_at__lte=end_time)
        
        # 根据粒径范围过滤（基于单个粒径大小）
        min_size = validated_data.get('min_size')
        if min_size is not None:
            detail_queryset = detail_queryset.filter(size__gte=min_size)
            
        max_size = validated_data.get('max_size')
        if max_size is not None:
            detail_queryset = detail_queryset.filter(size__lte=max_size)
        
        # 计算总数（只计算不同的 record_id 数量）
        total_count = detail_queryset.values('record_id').distinct().count()
        
        # 使用子查询获取符合条件的 record_id，然后直接在 AlgoRecord 上分页
        subquery = detail_queryset.values_list('record_id', flat=True).distinct()
        
        # 在 AlgoRecord 表上应用子查询过滤和分页
        record_queryset = AlgoRecord.objects.filter(id__in=subquery).order_by('-detected_at')
        
        # 应用分页：计算偏移量
        offset = (page - 1) * page_size
        paginated_records = record_queryset[offset:offset + page_size]
        
        # 如果当前页没有记录，返回空结果
        if not paginated_records:
            return Response({
                'count': total_count,
                'results': []
            })
        
        # 提取当前页的 record_id 列表
        current_page_record_ids = [record.id for record in paginated_records]
        
        # 批量获取当前页 record_id 的粒径统计
        size_stats = AlgoBigParticleDetail.objects.filter(
            record_id__in=current_page_record_ids
        ).values('record_id').annotate(
            min_size=models.Min('size'),
            max_size=models.Max('size')
        )
        
        # 创建粒径统计映射
        size_map = {stat['record_id']: stat for stat in size_stats}
        
        # 为每个记录附加粒径信息
        for record in paginated_records:
            stat = size_map.get(record.id, {})
            record._min_size = stat.get('min_size')
            record._max_size = stat.get('max_size')
        
        # 序列化数据
        serializer = self.get_serializer(paginated_records, many=True)
        
        # 返回自定义分页格式
        return Response({
            'count': total_count,
            'results': serializer.data
        })


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
        now = timezone.localtime(timezone.now())
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
                case_when_clauses.append(f"COUNT(CASE WHEN size >= {level} THEN 1 END) AS count_{level}")
            else:
                # 中间等级：>=当前等级且<下一等级
                next_level = size_levels[i + 1]
                case_when_clauses.append(f"COUNT(CASE WHEN size >= {level} AND size < {next_level} THEN 1 END) AS count_{level}")
        
        case_when_sql = ",\n                    ".join(case_when_clauses)
        
        # 执行两个 SQL 查询
        with connection.cursor() as cursor:
            # 查询1: 30秒内统计
            recent_sql = f"""
                SELECT 
                    stream_id,
                    {case_when_sql}
                FROM algo_big_particle_detail
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
                FROM algo_big_particle_detail
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
            
            # 计算占比
            recent_stats = self._calculate_stats_with_percentage(recent_data, size_levels)
            today_stats = self._calculate_stats_with_percentage(today_data, size_levels)
            
            # 构建该流的统计结果
            stream_stats = {
                "stream_id": stream_id,
                "stats": [
                    {
                        "range": "recent_30s",
                        "values": recent_stats
                    },
                    {
                        "range": "today", 
                        "values": today_stats
                    }
                ]
            }
            results.append(stream_stats)
        
        return Response({"results": results})
    
    def _calculate_stats_with_percentage(self, level_counts, size_levels):
        """计算各等级的数量和占比"""
        # 计算总数
        total_count = sum(level_counts.values())
        
        # 构建结果列表
        stats = []
        for level in size_levels:
            count = level_counts[str(level)]
            percentage = round((count / total_count * 100), 2) if total_count > 0 else 0.0
            
            stats.append({
                "level": level,
                "count": count,
                "percentage": percentage
            })
        
        return stats


class BigParticleHourlyStatsAPIView(APIView):
    """大颗粒按小时统计API视图"""

    def _get_size_levels(self):
        """从系统配置获取粒径等级"""
        big_particle_config = SystemConfig.objects.filter(
            config_type='algorithm',
            name='big_particle',
            is_active=True
        ).first()

        if not big_particle_config:
            raise ValidationError("未找到大颗粒算法配置")

        alarm_threshold = big_particle_config.config_data['alarm_threshold']
        # 从 alarm_threshold 中获取粒径等级，并排序
        size_levels = sorted([threshold['size_level'] for threshold in alarm_threshold])
        return size_levels

    def get(self, request):
        """获取指定日期和流ID的按小时统计数据"""
        # 验证查询参数
        query_serializer = BigParticleHourlyStatsQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            raise ValidationError(query_serializer.errors)

        stream_id = query_serializer.validated_data['stream_id']
        date = query_serializer.validated_data['date']

        # 获取动态粒径等级
        size_levels = self._get_size_levels()

        # 计算时间边界（指定日期的整天，使用当前时区）
        # 创建timezone-aware的datetime对象
        start_time = timezone.datetime.combine(date, timezone.datetime.min.time())
        start_time = timezone.make_aware(start_time, timezone.get_current_timezone())
        end_time = start_time + timedelta(days=1)

        # 根据等级动态构建CASE WHEN子句
        case_when_clauses = []
        for i, level in enumerate(size_levels):
            if i == len(size_levels) - 1:
                # 最后一个等级：>=该等级
                case_when_clauses.append(f"COUNT(CASE WHEN size >= {level} THEN 1 END) AS count_{i}")
            else:
                # 中间等级：>=当前等级且<下一等级
                next_level = size_levels[i + 1]
                case_when_clauses.append(f"COUNT(CASE WHEN size >= {level} AND size < {next_level} THEN 1 END) AS count_{i}")

        case_when_sql = ',\n                '.join(case_when_clauses)

        # 执行 SQL 查询
        with connection.cursor() as cursor:
            sql = f"""
            SELECT
                stream_id,
                DATE_TRUNC('hour', detected_at AT TIME ZONE 'Asia/Shanghai') AS hour_time,
                {case_when_sql}
            FROM algo_big_particle_detail
            WHERE stream_id = %s
            AND detected_at >= %s AND detected_at < %s
            GROUP BY stream_id, DATE_TRUNC('hour', detected_at AT TIME ZONE 'Asia/Shanghai')
            ORDER BY hour_time
            """

            cursor.execute(sql, (stream_id, start_time, end_time))
            rows = cursor.fetchall()

        # 构建响应数据
        hourly_stats = []
        num_size_ranges = len(size_levels)

        for row in rows:
            stream_id_result = row[0]
            hour_time = row[1]
            counts = list(row[2:2+num_size_ranges])  # 各尺寸范围的计数
            total_count = sum(counts)

            hour_str = hour_time.strftime('%H:00')

            # 构建尺寸范围数据，包含数量和百分比
            size_ranges = []
            for i, level in enumerate(size_levels):
                count = counts[i]
                percentage = round((count / total_count * 100), 2) if total_count > 200 else 0.0

                # 构建范围标签
                if i == len(size_levels) - 1:
                    range_label = f">={level}mm"
                else:
                    range_label = f"{level}-{size_levels[i+1]}mm"

                size_ranges.append({
                    "range": range_label,
                    "count": count,
                    "percentage": percentage
                })

            hourly_stats.append({
                "stream_id": stream_id_result,
                "hour": hour_str,
                "size_ranges": size_ranges,
                "total": total_count
            })

        return Response({
            "stream_id": stream_id,
            "date": date.strftime('%Y-%m-%d'),
            "hourly_stats": hourly_stats
        })


class BigParticleDailyStatsAPIView(APIView):
    """大颗粒按天统计API视图"""

    def _get_size_levels(self):
        """从系统配置获取粒径等级"""
        big_particle_config = SystemConfig.objects.filter(
            config_type='algorithm',
            name='big_particle',
            is_active=True
        ).first()

        if not big_particle_config:
            raise ValidationError("未找到大颗粒算法配置")

        alarm_threshold = big_particle_config.config_data['alarm_threshold']
        # 从 alarm_threshold 中获取粒径等级，并排序
        size_levels = sorted([threshold['size_level'] for threshold in alarm_threshold])
        return size_levels

    def get(self, request):
        """获取指定日期范围和流ID的按天统计数据"""
        # 验证查询参数
        query_serializer = BigParticleDailyStatsQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            raise ValidationError(query_serializer.errors)

        stream_id = query_serializer.validated_data['stream_id']
        start_date = query_serializer.validated_data['start_date']
        end_date = query_serializer.validated_data['end_date']
        end_date_excluded = end_date + timedelta(days=1)

        # 获取动态粒径等级
        size_levels = self._get_size_levels()

        # 根据等级动态构建CASE WHEN子句
        case_when_clauses = []
        for i, level in enumerate(size_levels):
            if i == len(size_levels) - 1:
                # 最后一个等级：>=该等级
                case_when_clauses.append(f"COUNT(CASE WHEN size >= {level} THEN 1 END) AS count_{i}")
            else:
                # 中间等级：>=当前等级且<下一等级
                next_level = size_levels[i + 1]
                case_when_clauses.append(f"COUNT(CASE WHEN size >= {level} AND size < {next_level} THEN 1 END) AS count_{i}")

        case_when_sql = ',\n                '.join(case_when_clauses)

        # 执行 SQL 查询（按天分组）
        with connection.cursor() as cursor:
            sql = f"""
            SELECT
                stream_id,
                DATE_TRUNC('day', detected_at AT TIME ZONE 'Asia/Shanghai') AS day_time,
                {case_when_sql}
            FROM algo_big_particle_detail
            WHERE stream_id = %s
            AND detected_at >= %s AND detected_at < %s
            GROUP BY stream_id, DATE_TRUNC('day', detected_at AT TIME ZONE 'Asia/Shanghai')
            ORDER BY day_time
            """

            cursor.execute(sql, (stream_id, start_date, end_date_excluded))
            rows = cursor.fetchall()

        # 构建响应数据
        daily_stats = []
        num_size_ranges = len(size_levels)

        for row in rows:
            stream_id_result = row[0]
            day_time = row[1]
            counts = list(row[2:2+num_size_ranges])  # 各尺寸范围的计数
            total_count = sum(counts)

            date_str = day_time.strftime('%Y-%m-%d')

            # 构建尺寸范围数据，包含数量和百分比
            size_ranges = []
            for i, level in enumerate(size_levels):
                count = counts[i]
                percentage = round((count / total_count * 100), 2) if total_count > 200 else 0.0

                # 构建范围标签
                if i == len(size_levels) - 1:
                    range_label = f">={level}mm"
                else:
                    range_label = f"{level}-{size_levels[i+1]}mm"

                size_ranges.append({
                    "range": range_label,
                    "count": count,
                    "percentage": percentage
                })

            daily_stats.append({
                "stream_id": stream_id_result,
                "date": date_str,
                "size_ranges": size_ranges,
                "total": total_count
            })

        return Response({
            "stream_id": stream_id,
            "start_date": start_date.strftime('%Y-%m-%d'),
            "end_date": end_date.strftime('%Y-%m-%d'),
            "daily_stats": daily_stats
        })


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


class AlgoBlacklistViewSet(viewsets.ModelViewSet):
    """算法黑名单视图集"""
    # TODO 算法加载黑名单，并进行过滤
    
    queryset = AlgoBlacklist.objects.all()
    serializer_class = AlgoBlacklistSerializer
    
    def get_queryset(self):
        """根据查询参数过滤黑名单"""
        queryset = self.queryset
        
        # 根据流ID过滤
        stream_id = self.request.query_params.get('stream_id')
        if stream_id:
            queryset = queryset.filter(stream_id=stream_id)
        
        # 根据算法名称过滤
        algo_name = self.request.query_params.get('algo_name')
        if algo_name:
            queryset = queryset.filter(algo_name=algo_name)
        
        # 根据是否启用过滤
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            if is_active.lower() in ['true', '1']:
                queryset = queryset.filter(is_active=True)
            elif is_active.lower() in ['false', '0']:
                queryset = queryset.filter(is_active=False)
        
        return queryset
    
    def perform_create(self, serializer):
        """创建黑名单"""
        validated_data = serializer.validated_data
        original_record_id = validated_data.pop('original_record_id')
        original_instance_id = validated_data.pop('original_instance_id')
        
        # 1. 根据 original_record_id 获取原始记录
        try:
            original_record = AlgoRecord.objects.get(id=original_record_id)
        except AlgoRecord.DoesNotExist:
            raise ValidationError(f"原始记录不存在: {original_record_id}")
        
        # 2. 从检测结果中提取对应实例
        if not original_record.result:
            raise ValidationError("原始记录中没有检测结果数据")
        
        target_instance = None
        for instance_data in original_record.result:
            if instance_data.get('id', None) == original_instance_id:
                target_instance = instance_data
                break
        
        if not target_instance:
            raise ValidationError(f"在检测结果中未找到 original_instance_id: {original_instance_id}")
        
        # 3. 获取原图并生成黑名单区域的渲染图和小图
        algo_name = 'big_particle'  # TODO 临时固定为 big_particle，后续根据记录获取算法名
        original_image_id = original_record.original_image_id
        rendered_image_id = None
        cropped_image_id = None
        
        # 获取原图
        original_oss = OssObject.objects.get(id=original_image_id)
        original_image_path = OSS_DIR / original_oss.file_path
        original_image = cv2.imread(str(original_image_path))

        # 提取边界框
        left = target_instance['left']
        top = target_instance['top']
        right = target_instance['right']
        bottom = target_instance['bottom']
        
        # 生成渲染图（在原图上画框）
        rendered_image = original_image.copy()
        cv2.rectangle(rendered_image, (left, top), (right, bottom), (0, 0, 255), 2)
        
        # 保存渲染图
        rendered_file_name = BLACKLIST_DIR / f"stream_{original_record.stream_id}_{original_record.id}_{original_instance_id}_rendered.jpg"
        rendered_image_id = save_image(rendered_image, rendered_file_name)
            
        # 裁剪小图（检测区域）
        cropped_image = original_image[top:bottom, left:right]
        # 保存小图
        cropped_file_name = BLACKLIST_DIR / f"stream_{original_record.stream_id}_{original_record.id}_{original_instance_id}_cropped.png"
        cropped_image_id = save_image(cropped_image, cropped_file_name)
        
        # 4. 保存黑名单记录
        serializer.save(
            stream_id=original_record.stream_id,
            stream_name=original_record.stream_name,
            algo_name=algo_name,
            bbox={'left': left, 'top': top, 'right': right, 'bottom': bottom},
            rendered_image_id=rendered_image_id,
            cropped_image_id=cropped_image_id,
            original_record_id=original_record_id,
            original_instance_id=original_instance_id,
            original_instance=target_instance
        )
    
    def perform_destroy(self, instance):
        """删除黑名单"""
        # 删除相关图片文件
        image_ids = []
        if instance.rendered_image_id:
            image_ids.append(instance.rendered_image_id)
        if instance.cropped_image_id:
            image_ids.append(instance.cropped_image_id)
        
        if image_ids:
            result = delete_oss_images(image_ids)
            logger.info(f"黑名单记录 {instance.id} 删除图片文件结果: "
                       f"成功 {result['deleted_count']} 个，失败 {result['failed_count']} 个")
        
        instance.delete()


class AlarmViewSet(viewsets.ReadOnlyModelViewSet):
    """告警查询视图集"""
    
    queryset = Alarm.objects.all()
    serializer_class = AlarmResponseSerializer
    
    def get_queryset(self):
        """根据查询参数过滤数据"""
        queryset = super().get_queryset()
        
        # 获取查询参数
        query_serializer = AlarmQuerySerializer(data=self.request.query_params)
        if not query_serializer.is_valid():
            raise ValidationError(query_serializer.errors)
        
        validated_data = query_serializer.validated_data
        
        # 根据流ID过滤
        stream_ids = validated_data.get('stream_ids')
        if stream_ids:
            queryset = queryset.filter(stream_id__in=stream_ids)
        
        # 根据告警类型过滤
        alarm_type = validated_data.get('alarm_type')
        if alarm_type:
            queryset = queryset.filter(alarm_type=alarm_type)
        
        # 根据时间范围过滤
        start_time = validated_data.get('start_time')
        if start_time:
            queryset = queryset.filter(alarm_time__gte=start_time)
            
        end_time = validated_data.get('end_time')
        if end_time:
            queryset = queryset.filter(alarm_time__lte=end_time)
        
        return queryset
