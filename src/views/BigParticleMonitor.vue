<script setup lang="ts">
import { ref, onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'
import { listVideoStreams, type VideoStreamItem } from '@/services/videostreams'
import { getActiveBigParticleAlgorithmConfig } from '@/services/systemConfigs'
import { getBigParticleStats } from '@/services/bigParticleStats'

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
const streamWithAlarms = ref<StreamWithAlarm[]>([])

// 配置与范围/统计
type RangeKey = 'recent_30s' | 'today'
const cardActiveRange = ref<Map<number, RangeKey>>(new Map())
const getCardRange = (streamId: number): RangeKey =>
  cardActiveRange.value.get(streamId) ?? 'recent_30s'
const setCardRange = (streamId: number, range: RangeKey) => {
  cardActiveRange.value.set(streamId, range)
}
const sizeLevels = ref<number[]>([])
const thresholds = ref<Map<number, { warning: number; error: number }>>(new Map())
type RangeStatsMap = { recent_30s: Map<number, number>; today: Map<number, number> }
type StreamStatsMap = Map<number, RangeStatsMap>
const streamStats = ref<StreamStatsMap>(new Map())

const createEmptyRangeStats = (): RangeStatsMap => ({
  recent_30s: new Map(),
  today: new Map(),
})

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
  for (const stream of streams) {
    if (stream.id === 4) {
      stream.enabled = true
    }
  }
  const ids = streams.map((s) => s.id)
  if (ids.length > 0) {
    // 获取统计数据
    const statsRes = await getBigParticleStats(ids)
    const nextStats: StreamStatsMap = new Map()
    const levelSet = new Set<number>()
    statsRes.results.forEach((item) => {
      const byRange = createEmptyRangeStats()
      item.stats.forEach((rangeItem) => {
        const key = rangeItem.range as RangeKey
        const map = key === 'today' ? byRange.today : byRange.recent_30s
        rangeItem.values.forEach((v) => {
          map.set(v.level, v.count)
          levelSet.add(v.level)
        })
      })
      nextStats.set(item.stream_id, byRange)
    })
    streamStats.value = nextStats

    // 与配置 level 比对，不一致则刷新配置并同步 sizeLevels
    const levelsFromStats = Array.from(levelSet).sort((a, b) => a - b)
    const arraysEqual = (a: number[], b: number[]) =>
      a.length === b.length && a.every((v, i) => v === b[i])
    if (sizeLevels.value.length === 0 || !arraysEqual(sizeLevels.value, levelsFromStats)) {
      // 获取配置
      const cfg = await getActiveBigParticleAlgorithmConfig()
      const threshold = cfg?.config_data?.alarm_threshold as Array<{
        size_level: number
        warning: number
        error: number
      }>
      const map = new Map<number, { warning: number; error: number }>()
      threshold.forEach((t) => map.set(t.size_level, { warning: t.warning, error: t.error }))
      thresholds.value = map
      sizeLevels.value = levelsFromStats
    }
  }

  // 组合数据并打标告警等级（基于 30s 内数据）
  streamWithAlarms.value = streams.map((stream) => {
    const level = evaluateStreamAlarm(stream.id)
    return { ...stream, alarmLevel: level }
  })
}

// 获取指定流在给定时间范围和级别的计数
const getCount = (streamId: number, range: RangeKey, level: number): number => {
  const entry = streamStats.value.get(streamId)
  if (!entry) return 0
  const map = range === 'today' ? entry.today : entry.recent_30s
  return map.get(level) ?? 0
}

// 计算单个级别的告警强度
const getLevelSeverity = (streamId: number, level: number): AlarmLevel => {
  const t = thresholds.value.get(level)
  if (!t) return 'ok'
  const count = getCount(streamId, 'recent_30s', level)
  if (count >= t.error) return 'error'
  if (count >= t.warning) return 'warning'
  return 'ok'
}

// 计算流的总体告警强度（取该范围内最高级别）
const evaluateStreamAlarm = (streamId: number): AlarmLevel => {
  let hasError = false
  let hasWarning = false
  sizeLevels.value.forEach((level) => {
    const sev = getLevelSeverity(streamId, level)
    if (sev === 'error') hasError = true
    else if (sev === 'warning') hasWarning = true
  })
  if (hasError) return 'error'
  if (hasWarning) return 'warning'
  return 'ok'
}

// 用于级别块的样式
const getLevelBoxClass = (streamId: number, level: number) => {
  if (getCardRange(streamId) === 'today') {
    return {}
  }
  const sev = getLevelSeverity(streamId, level)
  return {
    'is-warning': sev === 'warning',
    'is-error': sev === 'error',
  }
}

// 显示区间标签：非最后一档显示 a - bmm，最后一档显示 > amm
const formatLevelRangeLabel = (index: number): string => {
  const levels = sizeLevels.value
  if (index < 0 || index >= levels.length) return ''
  const current = levels[index]
  const isLast = index === levels.length - 1
  if (isLast) return `> ${current}mm`
  const next = levels[index + 1]
  return `${current} - ${next}mm`
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
      <div v-for="stream in streamWithAlarms" :key="stream.id" class="stream-card-item">
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
            <div class="card-content">
              <div class="range-toggle">
                <el-button
                  :type="getCardRange(stream.id) === 'recent_30s' ? 'primary' : 'default'"
                  @click="setCardRange(stream.id, 'recent_30s')"
                  >30秒内</el-button
                >
                <el-button
                  :type="getCardRange(stream.id) === 'today' ? 'primary' : 'default'"
                  @click="setCardRange(stream.id, 'today')"
                  >今日累计</el-button
                >
              </div>
              <div class="levels">
                <div
                  v-for="(level, idx) in sizeLevels"
                  :key="level"
                  class="level-box"
                  :class="getLevelBoxClass(stream.id, level)"
                >
                  <div class="level-label">{{ formatLevelRangeLabel(idx) }}</div>
                  <div class="level-count">
                    {{ getCount(stream.id, getCardRange(stream.id), level) }}
                  </div>
                </div>
              </div>
            </div>
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

.card-content {
  padding: 8px 0 4px;
}

.range-toggle {
  display: flex;
  justify-content: flex-start;
  margin-bottom: 8px;
}

.range-toggle .el-button {
  flex: 1;
  margin: 0;
}

.levels {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
  gap: 8px;
}

.level-box {
  border: 1px solid var(--el-border-color);
  padding: 8px 10px;
  background: var(--el-fill-color-light);
  transition: all 0.2s ease;
}

.level-box:hover {
  background: var(--el-fill-color-dark);
}

.level-box.is-warning {
  background: var(--el-color-warning-light-9);
  border-color: var(--el-color-warning);
}

.level-box.is-warning:hover {
  background: var(--el-color-warning-light-8);
}

.level-box.is-error {
  background: var(--el-color-danger-light-9);
  border-color: var(--el-color-danger);
}

.level-box.is-error:hover {
  background: var(--el-color-danger-light-8);
}

.level-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.level-count {
  font-size: 20px;
  font-weight: 600;
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
