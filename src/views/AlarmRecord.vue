<script setup lang="ts">
import { ref, onMounted } from 'vue'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import { listAlarms, type AlarmItem } from '@/services/alarms'
import { listVideoStreams, type VideoStreamItem } from '@/services/videostreams'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const alarmTypeMap = {
  big_particle: '大颗粒数量异常',
}

const loading = ref(true)
const page = ref(1)
const pageSize = 30
const total = ref(0)
const alarms = ref<AlarmItem[]>([])
const streams = ref<VideoStreamItem[]>([])
const filters = ref({
  streamIds: [] as number[],
  alarmType: undefined as string | undefined,
  timeRange: [] as [Date, Date] | [],
})

const startOf7DaysAgo = () => dayjs().subtract(7, 'day').startOf('day').toDate()
const endOfToday = () => dayjs().endOf('day').toDate()
filters.value.timeRange = [startOf7DaysAgo(), endOfToday()]

const formatLocalIso = (d?: Date) => (d ? dayjs(d).format('YYYY-MM-DDTHH:mm:ss') : undefined)

const fetchAlarms = async (newPage?: number) => {
  if (typeof newPage === 'number') page.value = newPage
  loading.value = true
  try {
    const [start, end] = (filters.value.timeRange as [Date, Date]) || []
    const res = await listAlarms({
      page: page.value,
      stream_ids: filters.value.streamIds,
      alarm_type: filters.value.alarmType || undefined,
      start_time: formatLocalIso(start),
      end_time: formatLocalIso(end),
    })
    total.value = res.count
    alarms.value = res.results
  } finally {
    loading.value = false
  }
}

const formatDateWithRelative = (iso: string) => {
  const abs = dayjs(iso).format('YYYY-MM-DD HH:mm:ss')
  const rel = dayjs(iso).fromNow()
  return `${abs} · ${rel}`
}

const resolveImageUrl = (path: string) => {
  if (!path) return ''
  if (import.meta.env.DEV) {
    return `http://192.168.3.13/storage/big-particle-data${path}`
  }
  return `${window.location.origin}${path}`
}

onMounted(async () => {
  try {
    const vs = await listVideoStreams()
    streams.value = vs.results
  } catch {
    // ignore
  }
  await fetchAlarms()
})

const displayAlarmType = (t: string) => alarmTypeMap[t as keyof typeof alarmTypeMap] || t
const isCountBased = (d: AlarmItem['data']) =>
  typeof d.error_count === 'number' || typeof d.count === 'number'
const formatPercent = (v?: number) => {
  if (typeof v !== 'number') return '-'
  const decimals = v < 10 ? 2 : 1
  return v.toFixed(decimals)
}
</script>

<template>
  <div class="alarm-page">
    <div class="filter-bar">
      <el-form inline @keyup.enter="fetchAlarms(1)">
        <el-form-item label="流">
          <el-select
            class="stream-select"
            v-model="filters.streamIds"
            clearable
            filterable
            multiple
            collapse-tags
            collapse-tags-tooltip
            :max-collapse-tags="2"
            placeholder="选择流"
          >
            <el-option v-for="s in streams" :key="s.id" :label="`${s.name}`" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="告警类型">
          <el-select v-model="filters.alarmType" clearable style="width: 180px" placeholder="全部">
            <el-option
              v-for="(label, value) in alarmTypeMap"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filters.timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            style="width: 350px; min-width: 350px"
            :default-time="[new Date(2000, 1, 1, 0, 0, 0), new Date(2000, 1, 1, 23, 59, 59)]"
          />
        </el-form-item>
        <el-form-item style="min-width: 132px; margin-right: 0">
          <el-button type="primary" @click="fetchAlarms(1)">查询</el-button>
          <el-button
            @click="
              () => {
                filters.streamIds = []
                filters.alarmType = undefined
                filters.timeRange = [startOf7DaysAgo(), endOfToday()]
                fetchAlarms(1)
              }
            "
            >重置</el-button
          >
        </el-form-item>
      </el-form>
    </div>
    <el-empty v-if="!loading && alarms.length === 0" description="暂无告警" />
    <div v-else class="alarm-grid">
      <div v-for="item in alarms" :key="item.id" class="alarm-item">
        <el-card shadow="never" class="alarm-card">
          <div class="card-top">
            <el-image class="img" :src="resolveImageUrl(item.alarm_image_url)" fit="contain">
              <template #error>
                <div class="image-fallback">图片已清理</div>
              </template>
            </el-image>
            <el-tag size="small" class="id-tag">ID: {{ item.id }}</el-tag>
          </div>
          <div class="card-body">
            <div class="alarm-type">
              <strong>{{ displayAlarmType(item.alarm_type) }}</strong>
            </div>
            <div class="detail-line">
              <span>粒径：{{ item.data.size_level }}mm</span>
              <template v-if="isCountBased(item.data)">
                <span>阈值：{{ item.data.error_count ?? '-' }}</span>
                <span>实际：{{ item.data.count ?? '-' }}</span>
              </template>
              <template v-else>
                <span>阈值：{{ formatPercent(item.data.error_percentage) }}%</span>
                <span>实际：{{ formatPercent(item.data.percentage) }}%</span>
              </template>
            </div>
            <div class="name-div">
              <span class="name weak">{{ item.stream_name }}</span>
              <span class="sid weak">ID: {{ item.stream_id }}</span>
            </div>
            <div class="time-line">
              <span class="weak">{{ formatDateWithRelative(item.alarm_time) }}</span>
            </div>
          </div>
        </el-card>
      </div>
    </div>

    <div class="pager">
      <el-pagination
        background
        layout="slot, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        v-model:current-page="page"
        @current-change="fetchAlarms"
      >
        <span>共 {{ total.toLocaleString() }} 条</span>
      </el-pagination>
    </div>
  </div>
</template>

<style scoped>
.alarm-page {
  padding-bottom: 20px;
}
.filter-bar {
  padding-top: 12px;
}
.filter-bar .el-form {
  display: flex;
  flex-wrap: wrap;
}
.filter-bar .stream-select {
  width: 300px;
}
.alarm-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
}
.alarm-card {
  position: relative;
  transition: all 0.2s ease;
  min-width: 220px;
  --el-card-padding: 0;
}
.alarm-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--el-box-shadow);
}
.card-top {
  position: relative;
  aspect-ratio: 16/9;
  background: var(--el-fill-color-light);
  display: flex;
  align-items: center;
  justify-content: center;
}
.card-top .img {
  width: 100%;
  height: 100%;
}
.image-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
}
.id-tag {
  position: absolute;
  right: 8px;
  top: 8px;
}
.card-body {
  padding: 8px 12px 12px;
}
.title-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.alarm-type {
  font-size: 16px;
}
.name-div {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: 8px;
}
.name-div .name {
  font-size: 14px;
}
.name-div .sid {
  font-size: 12px;
}
.time-line {
  font-size: 12px;
  margin-top: 8px;
}
.weak {
  color: var(--el-text-color-secondary);
}
.detail-line {
  margin-top: 4px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--el-text-color-regular);
  font-size: 13px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
