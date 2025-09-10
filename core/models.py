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


class AlgoRecord(models.Model):
    """
    算法检测记录表
    
    用于存储算法的检测结果。
    """
    
    # 关联信息（流删除后记录保留，仍可通过ID追溯）
    stream_id = models.PositiveIntegerField(
        help_text='所属视频流ID'
    )
    
    stream_name = models.CharField(
        max_length=100,
        help_text='视频流名称（冗余保存）'
    )

    algo_name = models.CharField(
        max_length=100,
        help_text='算法名称'
    )
    
    # 时间信息
    detected_at = models.DateTimeField(
        help_text='检测时间'
    )
    
    # 算法结果
    result = models.JSONField(
        null=True,
        help_text='算法结果（JSON格式）'
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
        db_table = 'core_algo_record'
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['detected_at', 'stream_id']),
            models.Index(fields=['detected_at', 'stream_name']),
            models.Index(fields=['detected_at', 'algo_name']),
        ]
        
    def __str__(self):
        return f'{self.stream_name} - {self.detected_at.strftime("%Y-%m-%d %H:%M:%S")}'


class AlgoBigParticleDetail(models.Model):
    """
    大颗粒检测详情表
    
    用于存储大颗粒算法的检测实例。
    """

    # 关联信息（流删除后记录保留，仍可通过ID追溯）
    stream_id = models.PositiveIntegerField(
        help_text='所属视频流ID'
    )
    
    stream_name = models.CharField(
        max_length=100,
        help_text='视频流名称（冗余保存）'
    )
    
    # 粒径尺寸（毫米为单位）
    size = models.PositiveIntegerField(
        help_text='粒径尺寸（毫米）'
    )
    
    # 算法记录 id
    record_id = models.PositiveIntegerField(
        help_text='算法记录ID'
    )
    
    # 检测实例
    instance = models.JSONField(
        null=True,
        help_text='检测实例'
    )
    
    # 时间信息
    detected_at = models.DateTimeField(
        help_text='检测时间'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='记录创建时间'
    )

    class Meta:
        db_table = 'algo_big_particle_detail'
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['detected_at', 'stream_id']),
            models.Index(fields=['detected_at', 'stream_name']),
            models.Index(fields=['detected_at', 'size']),
            models.Index(fields=['record_id']),
        ]

    def __str__(self):
        return f'{self.stream_name} - {self.detected_at.strftime("%Y-%m-%d %H:%M:%S")}'


class AlgoBlacklist(models.Model):
    """
    算法黑名单表
    
    用于存储需要过滤的检测区域，避免对固定静态区域的误报。
    通过 IoU 和直方图相似度来过滤检测结果。
    """
    
    # 关联信息
    stream_id = models.PositiveIntegerField(
        help_text='所属视频流ID'
    )
    
    stream_name = models.CharField(
        max_length=100,
        help_text='视频流名称（冗余保存）'
    )

    algo_name = models.CharField(
        max_length=50,
        help_text='算法名称'
    )

    # 黑名单区域
    bbox = models.JSONField(
        help_text='黑名单区域 {left, top, right, bottom}'
    )

    # 描述信息
    description = models.CharField(
        max_length=200,
        blank=True,
        help_text='描述信息'
    )
    
    # 过滤参数
    iou_threshold = models.FloatField(
        default=0.8,
        help_text='IoU阈值'
    )

    hist_threshold = models.FloatField(
        default=0.8,
        help_text='直方图相似度阈值'
    )

    # 关联图片
    rendered_image_id = models.PositiveIntegerField(
        help_text='黑名单区域渲染图OSS对象ID'
    )

    cropped_image_id = models.PositiveIntegerField(
        help_text='黑名单区域小图OSS对象ID'
    )

    # 原始记录
    original_record_id = models.PositiveIntegerField(
        help_text='原始记录ID'
    )

    original_instance_id = models.PositiveIntegerField(
        help_text='原始记录 instance id'
    )

    original_instance = models.JSONField(
        help_text='原始检测实例'
    )
    
    # 状态管理
    is_active = models.BooleanField(
        default=True,
        help_text='是否启用此黑名单规则'
    )
    
    # 时间信息
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='创建时间'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='更新时间'
    )
    
    class Meta:
        db_table = 'core_algo_blacklist'
        ordering = ['-created_at']
        
    def __str__(self):
        return f'{self.stream_name} - 黑名单区域 ({self.bbox})'


class OssObject(models.Model):
    """
    OSS对象表
    
    用于管理存储的文件。
    """

    # 存储类型
    class StorageType(models.TextChoices):
        LOCAL = 'local', '本地'
        OSS = 'oss', 'OSS'
    
    storage_type = models.CharField(
        max_length=20,
        choices=StorageType.choices,
        default=StorageType.LOCAL,
        help_text='存储类型'
    )
    
    # 文件信息
    bucket = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='存储桶'
    )

    file_path = models.CharField(
        max_length=500,
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


class SystemConfig(models.Model):
    """
    系统配置表
    
    用于存储各种系统配置，支持不同类型的配置。
    """
    
    config_type = models.CharField(
        max_length=50,
        help_text='配置类型'
    )
    
    name = models.CharField(
        max_length=100,
        help_text='配置名称'
    )
    
    description = models.TextField(
        blank=True,
        help_text='配置说明'
    )
    
    config_data = models.JSONField(
        default=dict,
        help_text='配置数据（JSON格式）'
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text='是否启用'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='创建时间'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='更新时间'
    )
    
    class Meta:
        db_table = 'core_system_config'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['config_type', 'name'],
                name='unique_config_type_name'
            )
        ]
        
    def __str__(self):
        return f'{self.config_type} - {self.name}'
    
    def get_config_value(self, key, default=None):
        """获取配置中的特定值"""
        return self.config_data.get(key, default)
    
    def set_config_value(self, key, value):
        """设置配置中的特定值"""
        self.config_data[key] = value
        
    @classmethod
    def get_config_by_type(cls, config_type, name=None):
        """根据类型获取配置"""
        query = cls.objects.filter(config_type=config_type, is_active=True)
        if name:
            query = query.filter(name=name)
        return query


class SystemState(models.Model):
    """
    系统运行状态记录表
    
    用于记录系统的各种状态信息，如清理进度等。
    """
    
    key = models.CharField(
        max_length=100,
        unique=True,
        help_text='状态键名'
    )
    
    value = models.JSONField(
        help_text='状态值'
    )
    
    description = models.TextField(
        blank=True,
        help_text='状态描述'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='更新时间'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='创建时间'
    )
    
    class Meta:
        db_table = 'core_system_state'
        
    def __str__(self):
        return f'{self.key}: {self.value[:50]}'
