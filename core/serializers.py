from django.contrib.auth.models import User, Group
from rest_framework import serializers
from .models import VideoStream


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
    
    def update(self, instance, validated_data):
        # 检查是否有需要重启的配置变更
        restart_required = False
        
        for field in self.RESTART_REQUIRED_FIELDS:
            if field in validated_data:
                old_value = getattr(instance, field)
                new_value = validated_data[field]
                if old_value != new_value:
                    restart_required = True
                    break
        
        # 检查 save_frames 字段变化
        save_frames_changed = False
        if 'save_frames' in validated_data:
            old_save_frames = getattr(instance, 'save_frames')
            new_save_frames = validated_data['save_frames']
            if old_save_frames != new_save_frames:
                save_frames_changed = True
        
        # 保存标记到实例，供 perform_update 使用
        instance._restart_required = restart_required
        instance._save_frames_changed = save_frames_changed
        
        return super().update(instance, validated_data)
    
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
        
        # 修改时不允许更新 type
        if self.instance and 'type' in data:
            data.pop('type')
        
        return data
