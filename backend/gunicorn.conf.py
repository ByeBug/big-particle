wsgi_app = "proj.wsgi:application"
worker_class = "gthread"
workers = 1
threads = 5
keepalive = 30
timeout = 30
graceful_timeout = 30
loglevel = "info"


def post_worker_init(worker):
    # worker 子进程启动后执行
    from core.runtime import start_background_services
    start_background_services()


def worker_exit(server, worker):
    # worker 退出时清理
    from core.runtime import stop_background_services
    stop_background_services()
