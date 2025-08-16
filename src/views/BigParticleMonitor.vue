<script setup lang="ts">
import { ref, onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'
import { listVideoStreams, type VideoStreamItem } from '@/services/videostreams'

// 监控数据
const monitorData = ref({
  particleCount: 0,
  temperature: '0.0',
  pressure: '0.00',
  flowRate: '0.0',
})

// 监控状态
const isMonitoring = ref(false)

// 定时器ID
let timer: number | null = null

// 流列表（仅存内存，不渲染）
type AlarmLevel = 'ok' | 'warning' | 'error'
type StreamWithAlarm = VideoStreamItem & { alarmLevel?: AlarmLevel }

const streamInfoAndStats = ref<StreamWithAlarm[]>([])

const getSeverityClass = (s: StreamWithAlarm) => {
  return `severity-${s.alarmLevel}`
}

const getStatusTagText = (s: StreamWithAlarm) => {
  if (s.status === 'disabled') return '未启用'
  if (s.status === 'abnormal') return '状态异常'
  return ''
}

const getStatusTagType = (s: StreamWithAlarm) => {
  if (s.status === 'disabled') return 'info'
  if (s.status === 'abnormal') return 'danger'
  return 'primary'
}

// 实时数据更新
const updateData = async () => {
  monitorData.value = {
    particleCount: Math.floor(Math.random() * 1000),
    temperature: (Math.random() * 100).toFixed(1),
    pressure: (Math.random() * 10).toFixed(2),
    flowRate: (Math.random() * 50).toFixed(1),
  }

  // 获取流列表
  const streamsRes = await listVideoStreams()
  const streams = streamsRes.results
  // TODO 获取统计数据
  // 组合数据
  streamInfoAndStats.value = streams.map((stream) => {
    if (stream.id === 4) {
      stream.enabled = true
    }
    let alarmLevel: AlarmLevel = 'ok'
    if (stream.id === 2) alarmLevel = 'warning'
    if (stream.id === 3) alarmLevel = 'error'
    return { ...stream, alarmLevel }
  })
}

// 启动定时器
const startTimer = () => {
  if (!timer) {
    console.log('🚀 开始实时监控')
    isMonitoring.value = true
    updateData()
    timer = setInterval(updateData, 2000) // 每2秒更新一次
  }
}

// 停止定时器
const stopTimer = () => {
  if (timer) {
    console.log('⏸️ 暂停实时监控')
    isMonitoring.value = false
    clearInterval(timer)
    timer = null
  }
}

// 组件挂载时启动定时器
onMounted(() => {
  console.log('📱 BigParticleMonitor 组件挂载')
  startTimer()
})

// 组件卸载时清理定时器（只在真正销毁时调用）
onUnmounted(() => {
  console.log('💀 BigParticleMonitor 组件销毁')
  stopTimer()
})

// KeepAlive 激活时启动定时器（从缓存恢复时执行）
onActivated(() => {
  console.log('✅ BigParticleMonitor 页面激活 - 恢复监控')
  startTimer()
})

// KeepAlive 失活时停止定时器
onDeactivated(() => {
  console.log('❌ BigParticleMonitor 页面失活 - 暂停监控')
  stopTimer()
})
</script>

<template>
  <div class="monitor-container">
    <div class="header">
      <h2>大颗粒实时监控</h2>
      <el-tag :type="isMonitoring ? 'success' : 'warning'" class="status-tag">
        <el-icon><component :is="isMonitoring ? 'VideoPlay' : 'VideoPause'" /></el-icon>
        {{ isMonitoring ? '实时监控中' : '监控已暂停' }}
      </el-tag>
    </div>

    <div class="stream-grid">
      <div v-for="stream in streamInfoAndStats" :key="stream.id" class="stream-card-item">
        <div
          class="stream-card-wrapper"
          :class="[getSeverityClass(stream), { 'is-disabled': !stream.enabled }]"
        >
          <i class="severity-bar" aria-hidden="true"></i>
          <el-card shadow="never">
            <template #header>
              <div class="stream-card-header">
                <div class="title-line">
                  <span class="name">{{ stream.name }}</span>
                  <el-tooltip
                    :disabled="!stream.status_message"
                    :content="stream.status_message"
                    :hide-after="0"
                    placement="bottom"
                    transition="none"
                  >
                    <el-tag v-if="getStatusTagText(stream)" :type="getStatusTagType(stream)">
                      {{ getStatusTagText(stream) }}
                    </el-tag>
                  </el-tooltip>
                </div>
                <div class="sub-line">{{ stream.ip }}</div>
              </div>
            </template>
            <!-- 内容留空 -->
            <template #footer>
              <!-- footer 留空 -->
            </template>
          </el-card>
        </div>
      </div>
    </div>

    <el-row :gutter="20">
      <el-col :span="6">
        <el-card>
          <template #header>
            <span>颗粒数量</span>
          </template>
          <div class="metric-value">{{ monitorData.particleCount }}</div>
          <div class="metric-unit">个</div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card>
          <template #header>
            <span>温度</span>
          </template>
          <div class="metric-value">{{ monitorData.temperature }}</div>
          <div class="metric-unit">°C</div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card>
          <template #header>
            <span>压力</span>
          </template>
          <div class="metric-value">{{ monitorData.pressure }}</div>
          <div class="metric-unit">MPa</div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card>
          <template #header>
            <span>流量</span>
          </template>
          <div class="metric-value">{{ monitorData.flowRate }}</div>
          <div class="metric-unit">L/min</div>
        </el-card>
      </el-col>
    </el-row>

    <div class="chart-container">
      <el-card>
        <template #header>
          <span>实时趋势图</span>
        </template>
        <div class="chart-placeholder">📊 这里将显示实时图表 (保持状态以避免重新渲染)</div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.stream-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.stream-card-wrapper {
  position: relative;
  transition: all 0.2s ease;
}

.stream-card-wrapper:hover {
  transform: translateY(-4px);
  box-shadow: var(--el-box-shadow);
}

.stream-card-wrapper.is-disabled {
  opacity: 0.6;
}

.stream-card-wrapper.is-disabled:hover {
  /* 保留交互与浮动，但弱化阴影 */
  box-shadow: var(--el-box-shadow-light);
}

.severity-bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 8px;
}

.stream-card-wrapper.severity-warning .severity-bar {
  background: var(--el-color-warning);
}
.stream-card-wrapper.severity-error .severity-bar {
  background: var(--el-color-danger);
}

.stream-card-header .title-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.stream-card-header .name {
  font-weight: 600;
}

.stream-card-header .sub-line {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 4px;
}
.monitor-container {
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.status-tag {
  font-size: 14px;
}

.metric-value {
  font-size: 24px;
  font-weight: bold;
  color: var(--el-color-primary);
  text-align: center;
}

.metric-unit {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  text-align: center;
  margin-top: 5px;
}

.chart-container {
  margin-top: 20px;
}

.chart-placeholder {
  height: 300px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 16px;
  color: var(--el-text-color-secondary);
}
</style>
