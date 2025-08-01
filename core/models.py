from django.db import models


class VideoStream(models.Model):
    class StreamType(models.TextChoices):
        # RTSP = 'rtsp', 'RTSP'
        MVS = 'mvs', 'MVS'
        VIDEO_FILE = 'video_file', 'Video File'
        IMAGE_DIR = 'image_dir', 'Image Dir'
        
    type = models.CharField(
        max_length=20,
        choices=StreamType.choices,
        default=StreamType.MVS,
        help_text='视频流类型'
    )
    
    ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text='视频流 IP'
    )
    
    address = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text='视频流地址'
    )
    
    width = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='视频宽度'
    )
    
    height = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='视频高度'
    )
    
    fps = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='采集帧率'
    )
    
    actual_fps = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='实际帧率'
    )
    
    enabled = models.BooleanField(
        default=True,
        help_text='是否启用'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        auto_now=True
    )
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.get_type_display()} - {self.ip}"
