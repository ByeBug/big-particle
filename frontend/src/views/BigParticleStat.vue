<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import type { ComposeOption } from 'echarts/core'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { listVideoStreams, type VideoStreamItem } from '@/services/videostreams'
import {
  getBigParticleHourlyStats,
  type BigParticleHourlyStatsResponse,
} from '@/services/bigParticleHourlyStats'
import {
  getBigParticleDailyStats,
  type BigParticleDailyStatsResponse,
} from '@/services/bigParticleDailyStats'

import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import type { LineSeriesOption } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  GraphicComponent,
} from 'echarts/components'
import type {
  TitleComponentOption,
  TooltipComponentOption,
  LegendComponentOption,
  GridComponentOption,
  GraphicComponentOption,
} from 'echarts/components'
import VChart from 'vue-echarts'

use([
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  GraphicComponent,
  LineChart,
  CanvasRenderer,
])

type AppEChartsOption = ComposeOption<
  | TitleComponentOption
  | TooltipComponentOption
  | LegendComponentOption
  | GridComponentOption
  | GraphicComponentOption
  | LineSeriesOption
>

// UI 状态
const loading = ref(false)
const streams = ref<VideoStreamItem[]>([])
const selectedStreamId = ref<number | null>(null)
const selectedDate = ref<Date>(new Date())

// Daily 独立筛选与状态
const loadingDaily = ref(false)
const dailyStreamId = ref<number | null>(null)
const dailyDateRange = ref<[Date, Date] | []>([
  dayjs().subtract(6, 'day').startOf('day').toDate(),
  dayjs().endOf('day').toDate(),
])

// 小工具
const formatDate = (d: Date) => dayjs(d).format('YYYY-MM-DD')
const hourTicks = Array.from({ length: 24 }).map((_, i) => `${String(i).padStart(2, '0')}:00`)
const getLast7DaysRange = (): [Date, Date] => [
  dayjs().subtract(6, 'day').startOf('day').toDate(),
  dayjs().endOf('day').toDate(),
]

// 拉取流列表
const fetchStreams = async () => {
  try {
    const res = await listVideoStreams()
    streams.value = res.results
    if (!selectedStreamId.value && streams.value.length > 0) {
      selectedStreamId.value = streams.value[0].id
    }
    if (!dailyStreamId.value && streams.value.length > 0) {
      dailyStreamId.value = streams.value[0].id
    }
  } catch {
    ElMessage.error('加载流列表失败')
  }
}

// 数据与图表
const hourlyRes = ref<BigParticleHourlyStatsResponse | null>(null)
const fetchHourly = async () => {
  if (!selectedStreamId.value) return
  loading.value = true
  try {
    hourlyRes.value = await getBigParticleHourlyStats({
      stream_id: selectedStreamId.value,
      date: formatDate(selectedDate.value),
    })
  } catch {
    ElMessage.error('加载按小时统计失败')
  } finally {
    loading.value = false
  }
}

type NumericOrDash = number | '-'
type SeriesMap = Record<string, NumericOrDash[]>
type CountMap = Record<string, NumericOrDash[]>

const seriesMap = computed<SeriesMap>(() => {
  const result: SeriesMap = {}
  const res = hourlyRes.value
  if (!res) return result

  // 先收集所有出现过的 range 作为系列
  const allRanges = new Set<string>()
  res.hourly_stats.forEach((h) => {
    h.size_ranges.forEach((r) => allRanges.add(r.range))
  })
  const ranges = Array.from(allRanges)
  ranges.forEach((r) => (result[r] = Array(24).fill('-')))

  // 将每小时的数据映射到 x 轴刻度索引
  const hourToIndex = new Map<string, number>()
  hourTicks.forEach((h, i) => hourToIndex.set(h, i))

  res.hourly_stats.forEach((h) => {
    const idx = hourToIndex.get(h.hour)
    if (idx === undefined) return
    h.size_ranges.forEach((r) => {
      if (!result[r.range]) result[r.range] = Array(24).fill('-')
      result[r.range][idx] =
        typeof r.percentage === 'number' ? Number(r.percentage.toFixed(2)) : '-'
    })
  })
  return result
})

const countsMap = computed<CountMap>(() => {
  const result: CountMap = {}
  const res = hourlyRes.value
  if (!res) return result
  const allRanges = new Set<string>()
  res.hourly_stats.forEach((h) => h.size_ranges.forEach((r) => allRanges.add(r.range)))
  const ranges = Array.from(allRanges)
  ranges.forEach((r) => (result[r] = Array(24).fill('-')))

  const hourToIndex = new Map<string, number>()
  hourTicks.forEach((h, i) => hourToIndex.set(h, i))
  res.hourly_stats.forEach((h) => {
    const idx = hourToIndex.get(h.hour)
    if (idx === undefined) return
    h.size_ranges.forEach((r) => {
      if (!result[r.range]) result[r.range] = Array(24).fill('-')
      result[r.range][idx] = typeof r.count === 'number' ? r.count : '-'
    })
  })
  return result
})

const chartOptions = computed<AppEChartsOption>(() => {
  const series: LineSeriesOption[] = Object.entries(seriesMap.value).map(([name, data]) => ({
    name,
    type: 'line' as const,
    data,
    connectNulls: false,
    emphasis: { focus: 'series' },
    smooth: false,
  }))
  const base: AppEChartsOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const list = Array.isArray(params) ? params : [params]
        const axisValue = (list[0] && (list[0] as { axisValue?: unknown }).axisValue) ?? ''
        const hourKey = String(axisValue)
        const hourLabel = hourKey
        const hourIdx = hourTicks.indexOf(hourKey)
        const lines = list.map((p) => {
          const marker = (p as { marker?: string }).marker || ''
          const name = (p as { seriesName?: string }).seriesName || ''
          const value = (p as { value?: unknown }).value
          const percentStr = typeof value === 'number' ? `${value}%` : '-'
          const countArr = countsMap.value[name as keyof typeof countsMap.value]
          const countVal = hourIdx >= 0 && countArr ? countArr[hourIdx] : '-'
          const countStr = typeof countVal === 'number' ? String(countVal) : '-'
          return `${marker}${name}: ${percentStr}（数量 ${countStr}）`
        })
        return [hourLabel, ...lines].join('<br/>')
      },
    },
    legend: { type: 'scroll', itemGap: 30 },
    grid: { left: 40, right: 20 },
    xAxis: {
      type: 'category',
      data: hourTicks,
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      splitNumber: 5,
      axisLabel: { formatter: '{value}%' },
      axisLine: { show: true },
      axisTick: { show: true },
      splitLine: { show: true },
    },
    series,
  }

  if (!hasData.value) {
    base.graphic = [
      {
        type: 'text',
        left: 'center',
        top: 'middle',
        silent: true,
        style: {
          text: '暂无数据',
          fill: '#999',
          fontSize: 14,
        },
      },
    ]
  }

  return base
})

// ===== 按天统计 =====
const dailyRes = ref<BigParticleDailyStatsResponse | null>(null)
const dailyTicks = computed<string[]>(() => {
  const range = dailyDateRange.value
  let start: Date
  let end: Date
  if (Array.isArray(range) && range.length === 2) {
    start = range[0]
    end = range[1]
  } else {
    const [s, e] = getLast7DaysRange()
    start = s
    end = e
  }
  const days: string[] = []
  let cur = dayjs(start).startOf('day')
  const endDay = dayjs(end).startOf('day')
  while (cur.isBefore(endDay) || cur.isSame(endDay)) {
    days.push(cur.format('YYYY-MM-DD'))
    cur = cur.add(1, 'day')
  }
  return days
})

const fetchDaily = async () => {
  if (!dailyStreamId.value) return
  const range = dailyDateRange.value
  const [defStart, defEnd] = getLast7DaysRange()
  const start = Array.isArray(range) && range.length === 2 ? range[0] : defStart
  const end = Array.isArray(range) && range.length === 2 ? range[1] : defEnd

  loadingDaily.value = true
  try {
    dailyRes.value = await getBigParticleDailyStats({
      stream_id: dailyStreamId.value,
      start_date: formatDate(start),
      end_date: formatDate(end),
    })
  } catch {
    ElMessage.error('加载按天统计失败')
  } finally {
    loadingDaily.value = false
  }
}

type DailySeriesMap = Record<string, NumericOrDash[]>
type DailyCountMap = Record<string, NumericOrDash[]>

const dailySeriesMap = computed<DailySeriesMap>(() => {
  const result: DailySeriesMap = {}
  const res = dailyRes.value
  const ticks = dailyTicks.value
  if (!res || ticks.length === 0) return result
  const allRanges = new Set<string>()
  res.daily_stats.forEach((d) => d.size_ranges.forEach((r) => allRanges.add(r.range)))
  const ranges = Array.from(allRanges)
  ranges.forEach((r) => (result[r] = Array(ticks.length).fill('-')))

  const dayToIndex = new Map<string, number>()
  ticks.forEach((d, i) => dayToIndex.set(d, i))
  res.daily_stats.forEach((d) => {
    const idx = dayToIndex.get(d.date)
    if (idx === undefined) return
    d.size_ranges.forEach((r) => {
      if (!result[r.range]) result[r.range] = Array(ticks.length).fill('-')
      result[r.range][idx] =
        typeof r.percentage === 'number' ? Number(r.percentage.toFixed(2)) : '-'
    })
  })
  return result
})

const dailyCountsMap = computed<DailyCountMap>(() => {
  const result: DailyCountMap = {}
  const res = dailyRes.value
  const ticks = dailyTicks.value
  if (!res || ticks.length === 0) return result
  const allRanges = new Set<string>()
  res.daily_stats.forEach((d) => d.size_ranges.forEach((r) => allRanges.add(r.range)))
  const ranges = Array.from(allRanges)
  ranges.forEach((r) => (result[r] = Array(ticks.length).fill('-')))

  const dayToIndex = new Map<string, number>()
  ticks.forEach((d, i) => dayToIndex.set(d, i))
  res.daily_stats.forEach((d) => {
    const idx = dayToIndex.get(d.date)
    if (idx === undefined) return
    d.size_ranges.forEach((r) => {
      if (!result[r.range]) result[r.range] = Array(ticks.length).fill('-')
      result[r.range][idx] = typeof r.count === 'number' ? r.count : '-'
    })
  })
  return result
})

const hasDailyData = computed(() => {
  const values = Object.values(dailySeriesMap.value)
  if (values.length === 0) return false
  return values.some((arr) => arr.some((v) => typeof v === 'number'))
})

const dailyChartOptions = computed<AppEChartsOption>(() => {
  const series: LineSeriesOption[] = Object.entries(dailySeriesMap.value).map(([name, data]) => ({
    name,
    type: 'line' as const,
    data,
    connectNulls: false,
    emphasis: { focus: 'series' },
    smooth: false,
  }))
  const base: AppEChartsOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const list = Array.isArray(params) ? params : [params]
        const axisValue = (list[0] && (list[0] as { axisValue?: unknown }).axisValue) ?? ''
        const dayKey = String(axisValue)
        const dayLabel = dayKey ? dayjs(dayKey).format('MM-DD') : ''
        const dayIdx = dailyTicks.value.indexOf(dayKey)
        const lines = list.map((p) => {
          const marker = (p as { marker?: string }).marker || ''
          const name = (p as { seriesName?: string }).seriesName || ''
          const value = (p as { value?: unknown }).value
          const percentStr = typeof value === 'number' ? `${value}%` : '-'
          const countArr = dailyCountsMap.value[name as keyof typeof dailyCountsMap.value]
          const countVal = dayIdx >= 0 && countArr ? countArr[dayIdx] : '-'
          const countStr = typeof countVal === 'number' ? String(countVal) : '-'
          return `${marker}${name}: ${percentStr}（数量 ${countStr}）`
        })
        return [dayLabel, ...lines].join('<br/>')
      },
    },
    legend: { type: 'scroll', itemGap: 30 },
    grid: { left: 40, right: 20 },
    xAxis: {
      type: 'category',
      data: dailyTicks.value,
      axisLabel: {
        formatter: (v: string) => (v ? dayjs(v).format('MM-DD') : v),
      },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      splitNumber: 5,
      axisLabel: { formatter: '{value}%' },
      axisLine: { show: true },
      axisTick: { show: true },
      splitLine: { show: true },
    },
    series,
  }

  if (!hasDailyData.value) {
    base.graphic = [
      {
        type: 'text',
        left: 'center',
        top: 'middle',
        silent: true,
        style: { text: '暂无数据', fill: '#999', fontSize: 14 },
      },
    ]
  }

  return base
})

onMounted(async () => {
  await fetchStreams()
})

// 自动刷新：切换流或日期立即刷新
watch(selectedStreamId, fetchHourly)
watch(selectedDate, fetchHourly)

watch(dailyStreamId, fetchDaily)
watch(dailyDateRange, fetchDaily)

// 是否有可展示数据（至少一个系列包含数字）
const hasData = computed(() => {
  const values = Object.values(seriesMap.value)
  if (values.length === 0) return false
  return values.some((arr) => arr.some((v) => typeof v === 'number'))
})
</script>

<template>
  <div class="stat-page">
    <div class="section-title">按小时统计</div>
    <div class="filter-bar">
      <el-form inline>
        <el-form-item label="流">
          <el-select v-model="selectedStreamId" style="width: 220px" placeholder="选择流">
            <el-option v-for="s in streams" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="selectedDate" type="date" placeholder="选择日期" />
        </el-form-item>
      </el-form>
    </div>

    <div class="chart-wrap">
      <v-chart :option="chartOptions" autoresize style="height: 420px" />
    </div>

    <div class="section-title" style="margin-top: 32px">按天统计</div>
    <div class="filter-bar">
      <el-form inline>
        <el-form-item label="流">
          <el-select v-model="dailyStreamId" style="width: 220px" placeholder="选择流">
            <el-option v-for="s in streams" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期范围">
          <el-date-picker
            v-model="dailyDateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            :default-time="[new Date(2000, 1, 1, 0, 0, 0), new Date(2000, 1, 1, 23, 59, 59)]"
          />
        </el-form-item>
      </el-form>
    </div>

    <div class="chart-wrap">
      <v-chart :option="dailyChartOptions" autoresize style="height: 420px" />
    </div>
  </div>
</template>

<style scoped>
.stat-page {
  padding: 16px;
}
.section-title {
  font-weight: 500;
  font-size: 20px;
  line-height: 22px;
  margin-bottom: 8px;
}
.filter-bar {
  margin-bottom: 4px;
}
.chart-wrap {
  background: #fff;
  border-radius: 6px;
  padding: 8px;
}
</style>
