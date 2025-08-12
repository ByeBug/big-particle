from django.db import models


class VideoStream(models.Model):
    class StreamType(models.TextChoices):
        RTSP = 'rtsp', 'RTSP'
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
        db_table = 'core_video_stream'
        ordering = ['-created_at']
        
    def __str__(self):
        return self.name


class AlgoBigParticleRecord(models.Model):
    """
    大颗粒检测记录表
    
    用于存储大颗粒算法的检测结果。
    使用 'algo_' 前缀区分算法特定表与通用业务表。
    """
    
    # 关联信息（流删除后记录保留，仍可通过ID追溯）
    stream_id = models.PositiveIntegerField(
        help_text='所属视频流ID'
    )
    
    stream_name = models.CharField(
        max_length=100,
        help_text='视频流名称（冗余保存）'
    )
    
    # 粒径信息（毫米为单位）
    min_size = models.PositiveIntegerField(
        help_text='最小粒径（毫米）'
    )
    
    max_size = models.PositiveIntegerField(
        help_text='最大粒径（毫米）'
    )
    
    # 时间信息
    detected_at = models.DateTimeField(
        help_text='检测时间'
    )
    
    # 图像关联
    original_image_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='原图OSS对象ID'
    )
    
    rendered_image_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='渲染图OSS对象ID'
    )
    
    # 记录创建时间
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='记录创建时间'
    )
    
    class Meta:
        db_table = 'algo_big_particle_record'
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['stream_id', 'detected_at']),
            models.Index(fields=['stream_name', 'detected_at']),
            models.Index(fields=['detected_at']),
            models.Index(fields=['max_size']),  # 按最大粒径查询
            models.Index(fields=['detected_at', 'max_size']),  # 时间+粒径组合查询
        ]
        
    def __str__(self):
        return f'{self.stream_name} - {self.detected_at.strftime("%Y-%m-%d %H:%M:%S")}'


class OssObject(models.Model):
    """
    OSS对象表
    
    用于管理本地存储的文件。
    """
    
    # 文件信息
    file_path = models.CharField(
        max_length=500,
        unique=True,
        help_text='文件存储路径'
    )
    
    file_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='原始文件名（可选）'
    )
    
    content_type = models.CharField(
        max_length=100,
        help_text='文件MIME类型'
    )
    
    # 状态管理
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='删除时间，为空表示未删除'
    )
    
    # 时间信息
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='创建时间'
    )
    
    class Meta:
        db_table = 'core_oss_object'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
        ]
        
    def __str__(self):
        name = self.file_name or self.file_path.split('/')[-1]
        return f'{name}'
    
    @property
    def is_deleted(self):
        """判断是否已删除"""
        return self.deleted_at is not None
    
    def get_url(self):
        """获取文件访问URL"""
        return f"/storage/oss/{self.file_path}"
