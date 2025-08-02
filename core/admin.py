from django.contrib import admin
from .models import VideoStream


@admin.register(VideoStream)
class VideoStreamAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'ip', 'address', 'fps', 'enabled', 'save_frames', 'status', 'created_at')
    list_filter = ('type', 'enabled', 'save_frames', 'status', 'created_at')
    search_fields = ('ip', 'address')
    readonly_fields = ('created_at', 'updated_at', 'width', 'height', 'status', 'status_message')
    ordering = ('-created_at',)
