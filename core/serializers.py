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


class VideoStreamSerializer(serializers.ModelSerializer):
    actual_fps = serializers.SerializerMethodField()
    
    class Meta:
        model = VideoStream
        fields = ['id', 'type', 'ip', 'address', 'width', 'height', 'fps', 'actual_fps', 'enabled', 'status', 'status_message', 'save_frames', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at', 'width', 'height', 'actual_fps', 'status', 'status_message']
    
    def get_actual_fps(self, obj):
        from .views import active_processors
        processor = active_processors.get(obj.id)
        if processor and hasattr(processor, 'get_actual_fps'):
            return processor.get_actual_fps()
        return None
    
    # 需要重启流的关键配置字段（宽高只读，不需要检测变化）
    RESTART_REQUIRED_FIELDS = ['ip', 'address', 'fps']
    
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
        
        # 修改时不允许更新 type（保持原有逻辑）
        if 'type' in validated_data:
            validated_data.pop('type')
        
        return super().update(instance, validated_data)
    
    def validate(self, data):
        type_value = data.get('type')
        ip = data.get('ip')
        address = data.get('address')
        
        # 添加时的验证
        if not self.instance:  # 创建时
            if type_value == 'mvs':
                if not ip:
                    raise serializers.ValidationError("MVS 类型必须提供 IP 地址")
            else:
                if not address:
                    raise serializers.ValidationError("非 MVS 类型必须提供 address")
        
        return data
    
    def update(self, instance, validated_data):
        # 修改时不允许更新 type
        if 'type' in validated_data:
            validated_data.pop('type')
        return super().update(instance, validated_data)
