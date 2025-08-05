from django.db import models


class VideoStream(models.Model):
    class StreamType(models.TextChoices):
        # RTSP = 'rtsp', 'RTSP'
        MVS = 'mvs', 'MVS'
        VIDEO_FILE = 'video_file', 'Video File'
        IMAGE_DIR = 'image_dir', 'Image Dir'
    
    class Status(models.TextChoices):
        DISABLED = 'disabled', '未启用'
        NORMAL = 'normal', '正常'
        ABNORMAL = 'abnormal', '异常'
        
    type = models.CharField(
        max_length=20,
        choices=StreamType.choices,
        default=StreamType.MVS,
        help_text='视频流类型'
    )
    
    name = models.CharField(
        max_length=100,
        help_text='视频流名称'
    )
    
    ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text='视频流 IP'
    )
    
    address = models.CharField(
        max_length=500,
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
    
    enabled = models.BooleanField(
        default=True,
        help_text='是否启用'
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DISABLED,
        help_text='运行状态'
    )
    
    status_message = models.TextField(
        blank=True,
        help_text='状态说明'
    )
    
    save_frames = models.BooleanField(
        default=False,
        help_text='是否保存帧为图片'
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
        return self.name
