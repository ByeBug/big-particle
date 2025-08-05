import signal
import sys
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    
    def ready(self):
        """Django 启动完成后执行"""
        # 注册信号处理器，确保 Django 关闭时清理资源
        self._register_signal_handlers()
        
        # 导入模型和处理器
        from .models import VideoStream
        from .stream.video_processor import create_processor, start_cleanup_thread
        
        # # 加载并启动所有启用的视频流
        # try:
        #     enabled_streams = VideoStream.objects.filter(enabled=True)
        #     for stream in enabled_streams:
        #         try:
        #             create_processor(stream)
        #             print(f"启动视频流: {stream.id} - {stream.type}")
        #         except Exception as e:
        #             print(f"启动视频流 {stream.id} 失败: {e}")
        # except Exception as e:
        #     # 数据库可能还未初始化，忽略错误
        #     print(f"加载视频流时出错（可能是数据库未初始化）: {e}")
        
        # 启动清理线程
        try:
            start_cleanup_thread()
        except Exception as e:
            print(f"启动清理线程失败: {e}")
    
    def _register_signal_handlers(self):
        """注册信号处理器"""
        def shutdown_handler(signum, frame):
            """处理关闭信号"""
            print(f"接收到信号 {signum}，正在关闭所有视频流...")
            try:
                from .stream.video_processor import shutdown_all_processors
                shutdown_all_processors()
            except Exception as e:
                print(f"关闭视频流时出错: {e}")
            
            # 调用默认的退出处理
            sys.exit(0)
        
        # 注册常见的退出信号
        signal.signal(signal.SIGTERM, shutdown_handler)  # 终止信号
        signal.signal(signal.SIGINT, shutdown_handler)   # Ctrl+C
        
        # 在 Windows 上也注册 SIGBREAK
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, shutdown_handler)
