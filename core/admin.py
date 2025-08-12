from django.contrib import admin
from .models import VideoStream, AlgoBigParticleRecord, OssObject, SystemConfig


@admin.register(VideoStream)
class VideoStreamAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'ip', 'address', 'fps', 'enabled', 'save_frames', 'status', 'created_at')
    list_filter = ('type', 'enabled', 'save_frames', 'status', 'created_at')
    search_fields = ('ip', 'address')
    readonly_fields = ('created_at', 'updated_at', 'width', 'height', 'status', 'status_message')
    ordering = ('-created_at',)


@admin.register(AlgoBigParticleRecord)
class AlgoBigParticleRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'stream_name', 'stream_id', 'min_size', 'max_size', 'detected_at', 'created_at')
    list_filter = ('stream_name', 'detected_at', 'created_at')
    search_fields = ('stream_name', 'stream_id')
    readonly_fields = ('created_at',)
    ordering = ('-detected_at',)
    date_hierarchy = 'detected_at'
    
    fieldsets = (
        ('基本信息', {
            'fields': ('stream_id', 'stream_name')
        }),
        ('粒径数据', {
            'fields': ('min_size', 'max_size')
        }),
        ('时间信息', {
            'fields': ('detected_at', 'created_at')
        }),
        ('图像关联', {
            'fields': ('original_image_id', 'rendered_image_id')
        }),
    )


@admin.register(OssObject)
class OssObjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'file_name', 'content_type', 'is_deleted', 'created_at')
    list_filter = ('content_type', 'deleted_at', 'created_at')
    search_fields = ('file_name', 'file_path')
    readonly_fields = ('created_at', 'is_deleted')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('文件信息', {
            'fields': ('file_path', 'file_name', 'content_type')
        }),
        ('状态管理', {
            'fields': ('deleted_at', 'is_deleted')
        }),
        ('时间信息', {
            'fields': ('created_at',)
        }),
    )
    
    def get_queryset(self, request):
        # 默认只显示未删除的文件，除非明确要求显示已删除文件
        qs = super().get_queryset(request)
        show_deleted = request.GET.get('deleted_at__isnull') == '0'  # 0 表示显示已删除文件
        
        if not show_deleted:
            qs = qs.filter(deleted_at__isnull=True)  # 只显示未删除文件
        
        return qs


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ('id', 'config_type', 'name', 'is_active', 'created_at', 'updated_at')
    list_filter = ('config_type', 'is_active', 'created_at', 'updated_at')
    search_fields = ('config_type', 'name', )
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('基本信息', {
            'fields': ('config_type', 'name', 'description', 'is_active')
        }),
        ('配置数据', {
            'fields': ('config_data',),
            'classes': ('wide',)
        }),
        ('时间信息', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        # 更新时 config_type 只读
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj:  # 编辑现有对象
            readonly_fields.append('config_type')
        return readonly_fields
