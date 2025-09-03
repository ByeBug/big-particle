# 大颗粒 django 后端

## TODO
- rtsp 流 decoder get_frame_with_timing 可能导致解码帧率比实际帧率低
- 推理线程定时输出日志，推理统计信息
- 编码线程
- Prometheus 指标
- systemctl stop gunicorn 导致的 paddle 报错
- nginx 部署后 drf 显示的链接不能直接使用
- 添加 WhiteNoise 使 gunicorn 支持静态文件？
- 大颗粒对上一帧去重，可能跳帧重复
- 定时读取黑名单，过滤模型结果
- oss 调整
  - 添加列 storage_type、bucket，以支持 oss 存储
  - 清理逻辑改为根据算法记录清理
- 通用算法记录表 + 特定算法记录表
- 告警表
  - 大颗粒告警
- 策略系统
  - 时间表
- 多机部署
  - 启动时读取或生成 machine_sn
  - 心跳接口和定时发送心跳
  - 流调度，一致性 hash
    - 跟流相关的操作都要分配到对应机器。启动停止、查看画面视频等
  - oss 分散存储，表中添加 machine_sn
