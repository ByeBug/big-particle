<script setup lang="ts">
import { ref, onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'
import dayjs from 'dayjs'
import { listVideoStreams, type VideoStreamItem } from '@/services/videostreams'
import { http } from '@/services/http'
import { useRouter } from 'vue-router'
import { getActiveBigParticleAlgorithmConfig } from '@/services/systemConfigs'
import { getBigParticleStats } from '@/services/bigParticleStats'

// 定时器ID
let timer: number | null = null
let isPolling = false

// 流列表（仅存内存，不渲染）
type AlarmLevel = 'ok' | 'warning' | 'error'
type StreamWithAlarm = VideoStreamItem & { alarmLevel?: AlarmLevel }
const streamWithAlarms = ref<StreamWithAlarm[]>([])
const serviceHealthy = ref(true)
const lastUpdatedAt = ref('')

const isClosed = (s: StreamWithAlarm) => !s.enabled || s.status === 'disabled'
const normalCount = ref(0)
const warningCount = ref(0)
const errorCount = ref(0)
const closedCount = ref(0)

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
const router = useRouter()

// 预览单帧图片
const framePreviewVisible = ref(false)
const framePreviewSrc = ref('')
const previewStreamId = ref<number | null>(null)

const buildLatestFrameUrl = (streamId: number, bust = true) => {
  let url = `${http.defaults.baseURL}/videostreams/${streamId}/latest_frame/`
  if (bust) url += `?ts=${Date.now()}`
  return url
}

const openLatestFrame = (streamId: number) => {
  framePreviewSrc.value = buildLatestFrameUrl(streamId)
  previewStreamId.value = streamId
  framePreviewVisible.value = true
}

const refreshLatestFrame = () => {
  if (previewStreamId.value == null) return
  framePreviewSrc.value = buildLatestFrameUrl(previewStreamId.value)
}

const canOpenImage = (s: StreamWithAlarm) => s.enabled && s.status == 'normal'

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

// 实时数据更新；返回是否成功
const updateData = async (): Promise<boolean> => {
  // 获取流列表
  try {
    const streamsRes = await listVideoStreams()
    const streams = streamsRes.results
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
    const combined = streams.map((stream: VideoStreamItem) => ({
      ...stream,
      alarmLevel: evaluateStreamAlarm(stream.id),
    }))
    streamWithAlarms.value = combined

    // 单次遍历统计四种状态数量
    let n = 0,
      w = 0,
      e = 0,
      c = 0
    for (const s of combined) {
      if (isClosed(s)) {
        c += 1
      } else if (s.status === 'abnormal' || s.alarmLevel === 'error') {
        e += 1
      } else if (s.alarmLevel === 'warning') {
        w += 1
      } else {
        n += 1
      }
    }
    normalCount.value = n
    warningCount.value = w
    errorCount.value = e
    closedCount.value = c

    serviceHealthy.value = true
    lastUpdatedAt.value = dayjs().format('YYYY-MM-DD HH:mm:ss')
    return true
  } catch {
    serviceHealthy.value = false
    return false
  }
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

// 跳转到记录页，带上筛选条件
const goToRecordWithFilters = (streamId: number, levelIndex: number) => {
  const levels = sizeLevels.value
  if (levelIndex < 0 || levelIndex >= levels.length) return
  const min = levels[levelIndex]
  const max = levelIndex === levels.length - 1 ? undefined : levels[levelIndex + 1]
  const now = dayjs()
  const range = getCardRange(streamId)
  const start = range === 'recent_30s' ? now.subtract(30, 'second') : now.startOf('day')
  const end = range === 'recent_30s' ? now : now.endOf('day')
  router.push({
    name: 'record',
    query: {
      stream_ids: String(streamId),
      min_max_size: String(min),
      ...(max ? { max_max_size: String(max) } : {}),
      start_time: start.format('YYYY-MM-DDTHH:mm:ss'),
      end_time: end.format('YYYY-MM-DDTHH:mm:ss'),
    },
  })
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

// 启动轮询：一次请求结束后再等待（成功2s，失败10s）
const startTimer = () => {
  if (isPolling) return
  console.log('🚀 开始实时监控')
  isPolling = true

  const loop = async () => {
    const ok = await updateData()
    if (!isPolling) return
    const delay = ok ? 2000 : 10000
    timer = window.setTimeout(loop, delay)
  }

  loop()
}

// 停止定时器
const stopTimer = () => {
  if (timer) {
    console.log('⏸️ 暂停实时监控')
    isPolling = false
    clearTimeout(timer)
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
      <div class="dots">
        <div class="dot-item normal">
          <i class="dot"></i>
          <span class="num">{{ normalCount }}</span>
          <span class="label">正常</span>
        </div>
        <div class="dot-item warning">
          <i class="dot"></i>
          <span class="num">{{ warningCount }}</span>
          <span class="label">警告</span>
        </div>
        <div class="dot-item error">
          <i class="dot"></i>
          <span class="num">{{ errorCount }}</span>
          <span class="label">错误</span>
        </div>
        <div class="dot-item closed">
          <i class="dot"></i>
          <span class="num">{{ closedCount }}</span>
          <span class="label">关闭</span>
        </div>
      </div>
      <div class="right-side">
        <el-tag :type="serviceHealthy ? 'success' : 'danger'" class="status-tag">
          {{ serviceHealthy ? '实时更新' : '服务异常' }}
        </el-tag>
        <span class="updated-at" v-if="lastUpdatedAt">更新：{{ lastUpdatedAt }}</span>
      </div>
    </div>

    <el-alert
      v-if="!serviceHealthy"
      title="服务异常：数据更新失败"
      type="error"
      show-icon
      :closable="false"
      class="global-alert"
    />

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
                  @click="goToRecordWithFilters(stream.id, idx)"
                >
                  <div class="level-label">{{ formatLevelRangeLabel(idx) }}</div>
                  <div class="level-count">
                    {{ getCount(stream.id, getCardRange(stream.id), level) }}
                  </div>
                </div>
              </div>
            </div>
            <template #footer>
              <el-button
                size="small"
                :disabled="!canOpenImage(stream)"
                @click="openLatestFrame(stream.id)"
                >查看图像</el-button
              >
            </template>
          </el-card>
        </div>
      </div>
    </div>
    <el-dialog v-model="framePreviewVisible" width="65%" top="5vh" :show-close="false">
      <div class="dialog-vertical">
        <div class="dialog-media">
          <el-image :src="framePreviewSrc" fit="contain" style="width: 100%; height: 100%" />
        </div>
        <div class="dialog-ops">
          <el-button @click="refreshLatestFrame">刷新</el-button>
        </div>
      </div>
    </el-dialog>
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
  cursor: pointer;
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
  padding-bottom: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-left: 18px;
}

.status-tag {
  font-size: 14px;
}

.dots {
  display: flex;
  gap: 16px;
}

.dot-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dot-item .dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}

.dot-item .num {
  display: inline-block;
  width: 24px; /* 固定宽度，避免跳动 */
  text-align: right;
  font-weight: 600;
}

.dot-item .label {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.dot-item.normal .dot {
  background: var(--el-color-success);
}
.dot-item.warning .dot {
  background: var(--el-color-warning);
}
.dot-item.error .dot {
  background: var(--el-color-danger);
}
.dot-item.closed .dot {
  background: var(--el-color-info);
}

.right-side {
  display: flex;
  align-items: center;
  gap: 12px;
}

.updated-at {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.global-alert {
  margin-bottom: 12px;
}

.dialog-vertical {
  /* 消除 dialog header 的 padding */
  margin-top: -16px;
}
.dialog-media {
  aspect-ratio: 16 / 9;
  background: var(--el-fill-color-light);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}
.dialog-ops {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
