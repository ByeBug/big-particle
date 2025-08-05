# CLAUDE.md

此文件为 Claude Code (claude.ai/code) 在此代码仓库中工作时提供指导。

- 用简体中文回复
- 遵循最佳实践，需求不合理时进行提示

## 项目概述

这是一个用于"大颗粒"检测系统的 Django REST API 后端，通过多个摄像头源处理视频流。系统管理来自不同源的视频流（MVS 相机、视频文件、图像目录），并通过 解码→推理→编码 流水线进行处理。

## 核心架构

### 视频流处理流水线
- **VideoStreamProcessor** (core/stream/video_processor.py)：三阶段多线程处理器：
  - 解码线程：从视频源读取帧
  - 推理线程：处理帧进行颗粒检测
  - 编码线程：输出处理后的视频（通过 DelayedQueue 延迟 500ms）
- **DelayedQueue** (core/stream/delayed_queue.py)：用于时间延迟处理的自定义队列实现
- 全局处理器注册表在 `active_processors` 字典中跟踪活跃视频流

### Django REST API 结构
- **VideoStream 模型** (core/models.py)：管理视频源配置，类型包括：MVS 相机、视频文件、图像目录
- **VideoStreamViewSet** (core/views.py)：CRUD 操作及自定义动作：
  - `open()`：启动视频处理
  - `close()`：停止视频处理
  - 自动管理：在启用/禁用时创建/销毁处理器
- 关键字段变更（ip、address、fps）时触发处理器热重启

### 数据库与基础设施
- PostgreSQL 数据库（端口 15432）与 pgAdmin4 网页界面（端口 8181）
- 中文本地化（zh-hans，Asia/Shanghai 时区）
- MVS SDK 集成路径：`/opt/MVS/Samples/64/Python/MvImport`

## 开发命令

### 数据库管理
```bash
# 启动数据库服务
docker-compose up -d

# 应用迁移
python manage.py migrate

# 创建超级用户
python manage.py createsuperuser
```

### 运行服务器
```bash
# 开发服务器
python manage.py runserver

# 使用自定义端口运行
python manage.py runserver 8080
```

### 测试
```bash
# 运行所有测试
python manage.py test

# 运行特定应用测试
python manage.py test core

# 使用覆盖率运行（如果已安装）
coverage run --source='.' manage.py test
coverage report
```

### 包管理
使用 uv 进行依赖管理：
```bash
# 安装依赖
uv sync

# 添加新依赖
uv add package-name

# 添加开发依赖
uv add --dev package-name
```

### 代码质量
```bash
# 类型检查（Pyright 配置在 pyproject.toml 中）
pyright

# Django 检查
python manage.py check
```

## 关键实现说明

### VideoStream 字段规则
- 所有类型都使用 `address` 字段作为地址
- MVS 类型的 `address` 必须是有效 IP，系统自动复制到 `ip` 字段
- `ip` 字段为只读，由系统自动维护
- 创建后不能修改 `type` 字段

### Serializer 开发规范
- **数据修改原则**：只在 `validate()` 方法中修改数据（如字段清理、自动设置等）
- **业务逻辑分离**：`create()`/`update()` 方法只处理业务逻辑，消费已处理好的 `validated_data`
- **验证流程**：字段验证 → 对象验证(`validate()`) → 数据保存(`create/update`)

### 处理器生命周期管理
- 当 VideoStream.enabled=True 时处理器自动启动
- 配置变更（address、fps）触发处理器重启
- 通过 API 端点手动开启/关闭
- 应用退出时关闭所有处理器

### 处理器更新策略
- **禁用→启用**：创建新处理器，使用最新配置，无需重启
- **启用→禁用**：销毁现有处理器
- **启用→启用**：根据配置变更决定是否重启
  - 配置变更（address、fps）：重启处理器
  - 仅 save_frames 变更：动态切换保存线程，无需重启
- **数据保存顺序**：先保存客户端数据，再执行处理器操作，最后更新状态

### 线程架构
- 每个 VideoStream 获得专用的解码/推理/编码线程
- 队列处理背压（推理队列大小 = fps，编码队列包含延迟缓冲）
- 优雅关闭，线程连接超时 5 秒

### API 端点
基础 URL：`/videostreams/`
- 标准 CRUD 操作
- `POST /videostreams/{id}/open/` - 开始处理
- `POST /videostreams/{id}/close/` - 停止处理
- 管理界面：`/admin/`
- API 浏览：`/api-auth/`