import re
import logging
from django.contrib.auth.models import User, Group
from rest_framework import serializers
from .models import VideoStream, AlgoRecord, AlgoBlacklist, OssObject, SystemConfig

logger = logging.getLogger(__name__)


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ['url', 'id', 'username', 'email', 'groups']


class GroupSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Group
        fields = ['url', 'id', 'name']


class VideoStreamSerializer(serializers.HyperlinkedModelSerializer):
    actual_fps = serializers.SerializerMethodField()
    
    class Meta:
        model = VideoStream
        fields = ['url', 'id', 'type', 'name', 'ip', 'address', 'width', 'height', 'fps', 'actual_fps',
                  'enabled', 'status', 'status_message', 'save_frames', 'created_at', 'updated_at']
        read_only_fields = ['url', 'created_at', 'updated_at', 'width', 'height', 'actual_fps', 'status', 'status_message', 'ip']
    
    def get_actual_fps(self, obj):
        from .stream.video_processor import active_processors
        processor = active_processors.get(obj.id)
        if processor and hasattr(processor, 'get_actual_fps'):
            return processor.get_actual_fps()
        return None
    
    # 需要重启流的关键配置字段（宽高只读，不需要检测变化）
    RESTART_REQUIRED_FIELDS = ['address', 'fps']
    
    def validate(self, data):
        import ipaddress
        
        # 清理所有字符串字段的前后空白
        for field, value in data.items():
            if isinstance(value, str):
                data[field] = value.strip()
        
        # 获取当前传入的数据
        input_type = data.get('type')
        input_name = data.get('name')
        input_address = data.get('address')
        input_fps = data.get('fps')
        
        # 确定最终的类型和地址用于验证
        if self.instance:  # 更新操作
            final_type = input_type or self.instance.type
            final_name = input_name or self.instance.name
            final_address = input_address or self.instance.address
            
            # 检查是否有需要重启的配置变更
            restart_required = False
            for field in self.RESTART_REQUIRED_FIELDS:
                if field in data:
                    old_value = getattr(self.instance, field)
                    new_value = data[field]
                    if old_value != new_value:
                        restart_required = True
                        break
            
            # 检查 save_frames 字段变化
            save_frames_changed = False
            if 'save_frames' in data:
                old_save_frames = getattr(self.instance, 'save_frames')
                new_save_frames = data['save_frames']
                if old_save_frames != new_save_frames:
                    save_frames_changed = True
            
            # 保存标记到实例，供 perform_update 使用
            self.instance._restart_required = restart_required
            self.instance._save_frames_changed = save_frames_changed
        else:  # 新建操作
            final_type = input_type
            final_name = input_name
            final_address = input_address
        
        # 新建时必须提供必填字段
        if not self.instance:
            if not final_name:
                raise serializers.ValidationError("必须提供有效的 name")
            if not final_address:
                raise serializers.ValidationError("必须提供有效的 address")
            # MVS 和 image_dir 类型必须提供 fps
            if final_type in ['mvs', 'image_dir'] and not input_fps:
                raise serializers.ValidationError(f"{final_type} 类型必须提供采集帧率 fps")
        
        # 验证传入的字段
        if input_name is not None and not input_name:
            raise serializers.ValidationError("name 不能为空")
        
        # 验证 name 唯一性
        if input_name:
            name_query = VideoStream.objects.filter(name=input_name)
            if self.instance:  # 更新时排除自己
                name_query = name_query.exclude(id=self.instance.id)
            if name_query.exists():
                raise serializers.ValidationError("该名称已存在，请使用其他名称")
        
        if input_fps is not None:
            if not isinstance(input_fps, int) or input_fps < 1 or input_fps > 60:
                raise serializers.ValidationError("fps 必须是 1-60 之间的整数")
        
        # 如果传入了 address，需要验证格式
        if input_address:
            # MVS 类型的 address 必须是有效 IP
            if final_type == 'mvs':
                try:
                    ipaddress.ip_address(input_address)
                except ValueError:
                    raise serializers.ValidationError("MVS 类型的 address 必须是有效的 IP 地址")
                # 自动设置 ip 字段
                data['ip'] = input_address
            
            # RTSP 类型的 address 必须以 rtsp:// 开头
            elif final_type == 'rtsp':
                if not input_address.startswith('rtsp://'):
                    raise serializers.ValidationError("RTSP 类型的 address 必须以 rtsp:// 开头")
                
                # 从RTSP URL中提取IP地址，支持带用户名密码的格式
                # 从最后一个@符号截断，避免用户名密码中的@干扰
                if '@' in input_address:
                    # 有@符号，从最后一个@后面开始解析
                    host_part = input_address.split('@')[-1]
                else:
                    # 没有@符号，去掉rtsp://前缀
                    host_part = input_address[7:]
                
                # 提取IP地址（去掉端口和路径）
                ip_pattern = r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
                match = re.search(ip_pattern, host_part)
                if match:
                    ip = match.group(1)
                    try:
                        ipaddress.ip_address(ip)
                        data['ip'] = ip
                    except ValueError:
                        pass  # IP格式无效，不设置ip字段
        
        # 修改时不允许更新 type
        if self.instance and 'type' in data:
            data.pop('type')
        
        return data


class BigParticleRecordQuerySerializer(serializers.Serializer):
    """大颗粒记录查询参数序列化器"""
    
    stream_ids = serializers.CharField(
        required=False,
        help_text='流ID列表（逗号分隔，如: 1,2,3 或单个值）'
    )
    
    stream_name = serializers.CharField(
        max_length=100,
        required=False,
        help_text='流名称（模糊匹配）'
    )
    
    start_time = serializers.DateTimeField(
        required=False,
        help_text='开始时间'
    )
    
    end_time = serializers.DateTimeField(
        required=False,
        help_text='结束时间'
    )
    
    min_size = serializers.IntegerField(
        required=False,
        help_text='粒径下限（毫米）'
    )
    
    max_size = serializers.IntegerField(
        required=False,
        help_text='粒径上限（毫米）'
    )
    
    def validate_stream_ids(self, value):
        """验证并解析流ID列表"""
        if not value:
            return []
            
        try:
            # 分割逗号分隔的字符串并转换为整数列表
            ids = [int(id_str.strip()) for id_str in value.split(',') if id_str.strip()]
            return ids
        except ValueError as e:
            raise serializers.ValidationError(f"流ID格式无效，请使用逗号分隔的整数: {e}")
    
    def validate_stream_name(self, value):
        """验证流名称"""
        if value:
            return value.strip()
        return value
    
    def validate_end_time(self, value):
        if value:
            return value.replace(microsecond=999999)
        return value


class BigParticleRecordResponseSerializer(serializers.ModelSerializer):
    """大颗粒记录响应序列化器"""
    
    min_size = serializers.SerializerMethodField()
    max_size = serializers.SerializerMethodField()
    original_image_url = serializers.SerializerMethodField()
    rendered_image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = AlgoRecord
        fields = [
            'id',
            'stream_id',
            'stream_name',
            'min_size',
            'max_size',
            'detected_at',
            'result',
            'original_image_url',
            'rendered_image_url'
        ]
    
    def get_min_size(self, obj):
        """获取预计算的最小粒径"""
        return getattr(obj, '_min_size', None)
    
    def get_max_size(self, obj):
        """获取预计算的最大粒径"""
        return getattr(obj, '_max_size', None)

    def get_original_image_url(self, obj):
        """获取原图URL"""
        if obj.original_image_id:
            try:
                oss_object = OssObject.objects.get(id=obj.original_image_id)
                return oss_object.get_url()
            except OssObject.DoesNotExist:
                logger.warning(f"原图OSS对象不存在: record_id={obj.id}, oss_id={obj.original_image_id}")
                return None
        return None
    
    def get_rendered_image_url(self, obj):
        """获取渲染图URL"""
        if obj.rendered_image_id:
            try:
                oss_object = OssObject.objects.get(id=obj.rendered_image_id)
                return oss_object.get_url()
            except OssObject.DoesNotExist:
                logger.warning(f"渲染图OSS对象不存在: record_id={obj.id}, oss_id={obj.rendered_image_id}")
                return None
        return None


class BigParticleStatsQuerySerializer(serializers.Serializer):
    """大颗粒统计查询参数序列化器"""
    
    stream_ids = serializers.CharField(
        required=True,
        help_text='流ID列表（逗号分隔，如: 1,2,3）'
    )
    
    def validate_stream_ids(self, value):
        """验证并解析流ID列表"""
        if not value:
            raise serializers.ValidationError("stream_ids 不能为空")
            
        # 去除首尾空格
        value = value.strip()
        if not value:
            raise serializers.ValidationError("stream_ids 不能为空")
            
        try:
            # 分割逗号分隔的字符串并转换为整数列表
            ids = [int(id_str.strip()) for id_str in value.split(',') if id_str.strip()]
            if not ids:
                raise serializers.ValidationError("stream_ids 不能为空")
            return ids
        except ValueError as e:
            raise serializers.ValidationError(f"流ID格式无效，请使用逗号分隔的整数: {e}")


class SystemConfigSerializer(serializers.HyperlinkedModelSerializer):
    """系统配置序列化器"""
    
    class Meta:
        model = SystemConfig
        fields = [
            'url',
            'id',
            'config_type',
            'name', 
            'description',
            'config_data',
            'is_active',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['url', 'id', 'created_at', 'updated_at']
    
    def validate(self, data):
        # 清理字符串字段的前后空白
        for field in ['config_type', 'name', 'description']:
            if field in data and isinstance(data[field], str):
                data[field] = data[field].strip()
        
        # 验证必填字段
        config_type = data.get('config_type')
        name = data.get('name')
        
        if not self.instance:  # 新建时
            if not config_type:
                raise serializers.ValidationError("config_type 不能为空")
            if not name:
                raise serializers.ValidationError("name 不能为空")
        else:  # 更新时
            # 不允许更新 config_type
            if 'config_type' in data:
                data.pop('config_type')
            # 使用实例的 config_type 进行唯一性验证
            config_type = self.instance.config_type
        
        # 验证唯一性约束 (config_type + name)
        if config_type and name:
            query = SystemConfig.objects.filter(
                config_type=config_type, 
                name=name
            )
            if self.instance:  # 更新时排除自己
                query = query.exclude(id=self.instance.id)
            if query.exists():
                raise serializers.ValidationError(
                    f"配置类型 '{config_type}' 下已存在名称为 '{name}' 的配置"
                )
        
        # 验证 config_data
        config_data = data.get('config_data')
        if config_data:
            if not isinstance(config_data, dict):
                raise serializers.ValidationError("config_data 必须是字典")
            
            threshold = config_data.get('threshold')
            if threshold is None:
                raise serializers.ValidationError("config_data 必须包含 threshold 字段")
            if not isinstance(threshold, float):
                raise serializers.ValidationError("threshold 必须是浮点数")
            if threshold < 0.5 or threshold > 1:
                raise serializers.ValidationError("threshold 必须在 0.5 到 1 之间")

            if self.instance.name == 'big_particle':
                alarm_threshold = config_data.get('alarm_threshold')
                if alarm_threshold is None:
                    raise serializers.ValidationError("config_data 必须包含 alarm_threshold 字段")
                if not isinstance(alarm_threshold, list):
                    raise serializers.ValidationError("alarm_threshold 必须是列表")
                if len(alarm_threshold) < 1 or len(alarm_threshold) > 5:
                    raise serializers.ValidationError("alarm_threshold 必须包含 1-5 个等级")
                existing_size_levels = set()
                for threshold in alarm_threshold:
                    if not isinstance(threshold, dict):
                        raise serializers.ValidationError(f"threshold 必须是字典: {threshold}")
                    
                    if not 'size_level' in threshold:
                        raise serializers.ValidationError(f"threshold 必须包含 size_level 字段: {threshold}")
                    size_level = threshold.get('size_level')
                    if size_level in existing_size_levels:
                        raise serializers.ValidationError(f"size_level 不能重复: {size_level}")
                    existing_size_levels.add(size_level)
                    if not isinstance(size_level, int):
                        raise serializers.ValidationError(f"size_level 必须是整数: {size_level}")
                    if size_level < 0:
                        raise serializers.ValidationError(f"size_level 必须大于 0: {size_level}")
                    
                    if not 'warning' in threshold or not 'error' in threshold:
                        raise serializers.ValidationError(f"threshold 必须包含 warning 和 error 字段: {threshold}")
                    warning_threshold = threshold.get('warning')
                    error_threshold = threshold.get('error')
                    if not isinstance(warning_threshold, int):
                        raise serializers.ValidationError(f"warning 必须是整数: {warning_threshold}")
                    if not isinstance(error_threshold, int):
                        raise serializers.ValidationError(f"error 必须是整数: {error_threshold}")
                    if warning_threshold <= 0:
                        raise serializers.ValidationError(f"warning 必须大于 0: {warning_threshold}")
                    if error_threshold <= 0:
                        raise serializers.ValidationError(f"error 必须大于 0: {error_threshold}")
                    if warning_threshold > error_threshold:
                        raise serializers.ValidationError(f"warning 必须小于等于 error: {warning_threshold} > {error_threshold}")
                
                config_data['alarm_threshold'] = sorted(alarm_threshold, key=lambda x: x['size_level'])

        return data


class AlgoBlacklistSerializer(serializers.HyperlinkedModelSerializer):
    """算法黑名单序列化器"""
    
    rendered_image_url = serializers.SerializerMethodField()
    cropped_image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = AlgoBlacklist
        fields = [
            'url',
            'id',
            'stream_id',
            'stream_name',
            'algo_name',
            'bbox',
            'description',
            'iou_threshold',
            'hist_threshold',
            'rendered_image_url',
            'cropped_image_url',
            'rendered_image_id',
            'cropped_image_id',
            'original_record_id',
            'original_instance_id',
            'original_instance',
            'is_active',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'url', 'id', 'stream_id', 'stream_name', 'algo_name', 'bbox',
            'rendered_image_url', 'cropped_image_url', 'rendered_image_id', 
            'cropped_image_id', 'original_instance', 'created_at', 'updated_at'
        ]
    
    def validate(self, data):
        """验证数据"""
        if not self.instance:  # 创建操作
            # 创建时必须提供 original_record_id 和 original_instance_id
            if 'original_record_id' not in data:
                raise serializers.ValidationError("创建黑名单时必须提供 original_record_id")
            if 'original_instance_id' not in data:
                raise serializers.ValidationError("创建黑名单时必须提供 original_instance_id")
            
            # 检查 original_record_id 和 original_instance_id 的组合是否已存在
            original_record_id = data['original_record_id']
            original_instance_id = data['original_instance_id']
            
            existing = AlgoBlacklist.objects.filter(
                original_record_id=original_record_id,
                original_instance_id=original_instance_id
            ).exists()
            
            if existing:
                raise serializers.ValidationError(
                    f"记录ID {original_record_id} + 实例ID {original_instance_id} 已在黑名单中"
                )
        else:  # 更新操作
            # 忽略传入的 original_record_id 和 original_instance_id，不允许修改
            data.pop('original_record_id', None)
            data.pop('original_instance_id', None)
        
        if 'description' in data:
            data['description'] = data['description'].strip()
        
        return data
    
    def get_rendered_image_url(self, obj):
        """获取渲染图URL"""
        if obj.rendered_image_id:
            try:
                oss_object = OssObject.objects.get(id=obj.rendered_image_id)
                return oss_object.get_url()
            except OssObject.DoesNotExist:
                logger.warning(f"渲染图OSS对象不存在: blacklist_id={obj.id}, oss_id={obj.rendered_image_id}")
                return None
        return None
    
    def get_cropped_image_url(self, obj):
        """获取小图URL"""
        if obj.cropped_image_id:
            try:
                oss_object = OssObject.objects.get(id=obj.cropped_image_id)
                return oss_object.get_url()
            except OssObject.DoesNotExist:
                logger.warning(f"小图OSS对象不存在: blacklist_id={obj.id}, oss_id={obj.cropped_image_id}")
                return None
        return None
