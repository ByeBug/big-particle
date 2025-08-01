from django.contrib import admin
from .models import VideoStream


@admin.register(VideoStream)
class VideoStreamAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'ip', 'address', 'fps', 'actual_fps', 'enabled', 'created_at')
    list_filter = ('type', 'enabled', 'created_at')
    search_fields = ('ip', 'address')
    readonly_fields = ('created_at', 'updated_at', 'width', 'height', 'actual_fps')
    ordering = ('-created_at',)
