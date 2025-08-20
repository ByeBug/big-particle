<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import { ElMessage } from 'element-plus'
import { listBigParticleRecords, type BigParticleRecordItem } from '@/services/bigParticleRecords'
import { listVideoStreams, type VideoStreamItem } from '@/services/videostreams'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const loading = ref(true) // 初始设置 loading 为 true，避免闪现暂无记录
const page = ref(1)
const pageSize = 30
const total = ref(0)
const records = ref<BigParticleRecordItem[]>([])
const previewVisible = ref(false)
const selectedRecord = ref<BigParticleRecordItem | null>(null)

// 过滤表单
const streams = ref<VideoStreamItem[]>([])
const filters = ref({
  streamIds: [] as number[],
  minMaxSize: undefined as number | undefined,
  maxMaxSize: undefined as number | undefined,
  timeRange: [] as [Date, Date] | [],
})

const startOf7DaysAgo = () => dayjs().subtract(7, 'day').startOf('day').toDate()
const endOfToday = () => dayjs().endOf('day').toDate()
// 默认最近7天
filters.value.timeRange = [startOf7DaysAgo(), endOfToday()]

const formatLocalIso = (d?: Date) => (d ? dayjs(d).format('YYYY-MM-DDTHH:mm:ss') : undefined)

const fetchRecords = async (newPage?: number) => {
  if (typeof newPage === 'number') page.value = newPage
  loading.value = true
  try {
    const [start, end] = (filters.value.timeRange as [Date, Date]) || []
    const res = await listBigParticleRecords({
      page: page.value,
      stream_ids: filters.value.streamIds,
      min_max_size: filters.value.minMaxSize,
      max_max_size: filters.value.maxMaxSize,
      start_time: formatLocalIso(start),
      end_time: formatLocalIso(end),
    })
    total.value = res.count
    records.value = res.results
  } finally {
    loading.value = false
  }
}

const formatSize = (minSize: number, maxSize: number) => {
  return minSize === maxSize ? `${maxSize}` : `${minSize}-${maxSize}`
}

const formatDateWithRelative = (iso: string) => {
  const abs = dayjs(iso).format('YYYY-MM-DD HH:mm:ss')
  const rel = dayjs(iso).fromNow()
  return `${abs} · ${rel}`
}

onMounted(async () => {
  // 初始化流选项与数据
  try {
    const vs = await listVideoStreams()
    streams.value = vs.results
  } catch {
    // ignore
  }
  await fetchRecords()
})

const resolveImageUrl = (path: string) => {
  if (!path) return ''
  // TODO 返回临时拼接的 url
  return `http://192.168.3.13/storage/big-particle-data${path}`
}

type PreviewMode = 'rendered' | 'original'
const previewMode = ref<PreviewMode>('rendered')
const selectedIndex = ref<number>(-1)

const openPreview = (rec: BigParticleRecordItem) => {
  selectedRecord.value = rec
  previewMode.value = 'rendered'
  previewVisible.value = true
  selectedIndex.value = records.value.findIndex((r) => r.id === rec.id)
}

const switchMode = (mode: PreviewMode) => {
  if (!selectedRecord.value) return
  previewMode.value = mode
}

const renderedUrl = computed(() =>
  selectedRecord.value ? resolveImageUrl(selectedRecord.value.rendered_image_url) : '',
)
const originalUrl = computed(() =>
  selectedRecord.value ? resolveImageUrl(selectedRecord.value.original_image_url) : '',
)
const currentUrl = computed(() =>
  previewMode.value === 'rendered' ? renderedUrl.value : originalUrl.value,
)

const copyLink = async () => {
  if (!currentUrl.value) return
  await navigator.clipboard.writeText(currentUrl.value)
  ElMessage.success('图片链接已复制')
}

const pageCount = computed(() => Math.ceil(total.value / pageSize))
const canPrev = computed(() => !(page.value === 1 && selectedIndex.value <= 0))
const canNext = computed(
  () => !(page.value === pageCount.value && selectedIndex.value >= records.value.length - 1),
)

const moveTo = async (delta: number) => {
  let newIndex = selectedIndex.value + delta
  // 换页到上一页尾或下一页首
  if (newIndex < 0) {
    if (page.value === 1) return
    await fetchRecords(page.value - 1)
    newIndex = records.value.length - 1
  } else if (newIndex >= records.value.length) {
    if (page.value >= pageCount.value) return
    await fetchRecords(page.value + 1)
    newIndex = 0
  }
  selectedIndex.value = newIndex
  selectedRecord.value = records.value[selectedIndex.value] || null
}

const prevRecord = () => moveTo(-1)
const nextRecord = () => moveTo(1)
</script>

<template>
  <div class="record-page">
    <div class="filter-bar">
      <el-form inline @keyup.enter="fetchRecords(1)">
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
        <el-form-item label="粒径范围" style="min-width: 290px">
          <el-input-number
            v-model="filters.minMaxSize"
            class="max-size-input"
            :min="0"
            placeholder="最小"
            precision="0"
            :controls="false"
          />
          <span class="range-sep">-</span>
          <el-input-number
            v-model="filters.maxMaxSize"
            class="max-size-input"
            :min="0"
            placeholder="最大"
            precision="0"
            :controls="false"
          />
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
          <el-button type="primary" @click="fetchRecords(1)">查询</el-button>
          <el-button
            @click="
              () => {
                filters.streamIds = []
                filters.minMaxSize = undefined
                filters.maxMaxSize = undefined
                filters.timeRange = [startOf7DaysAgo(), endOfToday()]
                fetchRecords(1)
              }
            "
            >重置</el-button
          >
        </el-form-item>
      </el-form>
    </div>
    <el-empty v-if="!loading && records.length === 0" description="暂无记录" />
    <div v-else class="record-grid">
      <div v-for="item in records" :key="item.id" class="record-item">
        <el-card shadow="never" class="record-card">
          <div class="card-top" @click="openPreview(item)">
            <!-- element 2.10.7 预览不能设置初始缩放，图片太大占满屏幕，因此不开启预览 -->
            <el-image class="img" :src="resolveImageUrl(item.rendered_image_url)" fit="contain">
              <template #error>
                <div class="image-fallback">图片已清理</div>
              </template>
            </el-image>
            <el-tag size="small" class="id-tag">ID: {{ item.id }}</el-tag>
          </div>
          <div class="card-body">
            <div class="title-line">
              <div class="name-div">
                <span class="name">{{ item.stream_name }}</span>
                <span class="sid">ID: {{ item.stream_id }}</span>
              </div>
              <span class="size">
                {{ formatSize(item.min_size, item.max_size) }}<small> mm</small>
              </span>
            </div>
            <div class="time-line">
              <span>{{ formatDateWithRelative(item.detected_at) }}</span>
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
        @current-change="fetchRecords"
      >
        <span>共 {{ total.toLocaleString() }} 条</span>
      </el-pagination>
    </div>

    <el-dialog v-model="previewVisible" width="65%" top="5vh" :show-close="false">
      <div class="dialog-vertical">
        <div class="dialog-media">
          <!-- 双层图片：叠放切换避免闪烁，不使用 lazy -->
          <el-image
            class="preview-img layer"
            :src="renderedUrl"
            fit="contain"
            :style="{ opacity: previewMode === 'rendered' ? 1 : 0 }"
          />
          <el-image
            class="preview-img layer"
            :src="originalUrl"
            fit="contain"
            :style="{ opacity: previewMode === 'original' ? 1 : 0 }"
          />
        </div>
        <div class="dialog-meta">
          <div class="meta-info">
            <div class="meta-div">
              <div class="label">流信息</div>
              <div class="name-div">
                <span class="name">{{ selectedRecord?.stream_name }}</span>
                <span class="sid">ID: {{ selectedRecord?.stream_id }}</span>
              </div>
            </div>
            <div class="meta-div">
              <div class="label">粒径</div>
              <div class="size">
                {{
                  selectedRecord ? formatSize(selectedRecord.min_size, selectedRecord.max_size) : ''
                }}
                <small> mm</small>
              </div>
            </div>
            <div class="meta-div">
              <div class="label">记录ID</div>
              <div class="value">{{ selectedRecord?.id }}</div>
            </div>
            <div class="meta-div">
              <div class="label">检测时间</div>
              <div class="value">
                {{ selectedRecord ? formatDateWithRelative(selectedRecord.detected_at) : '' }}
              </div>
            </div>
          </div>

          <div class="meta-ops">
            <div class="btn-group">
              <el-button @click="prevRecord" :disabled="!canPrev">上一条</el-button>
              <el-button @click="nextRecord" :disabled="!canNext">下一条</el-button>
            </div>
            <div class="btn-group">
              <el-button
                :type="previewMode === 'rendered' ? 'primary' : 'default'"
                @click="switchMode('rendered')"
                >渲染图</el-button
              >
              <el-button
                :type="previewMode === 'original' ? 'primary' : 'default'"
                @click="switchMode('original')"
                >原图</el-button
              >
            </div>
            <div class="btn-group">
              <el-link class="ops-link" type="primary" :underline="false" @click="copyLink"
                >复制图片链接</el-link
              >
              <el-link
                class="ops-link"
                type="primary"
                :underline="false"
                :href="currentUrl + '?download=true'"
                download
                target="_blank"
                rel="noopener"
                >下载图片</el-link
              >
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.record-page {
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
.filter-bar .range-sep {
  display: inline-block;
  padding: 0 8px;
  color: var(--el-text-color-secondary);
}
.filter-bar .max-size-input {
  width: 100px;
}
.record-grid {
  display: grid;
  /* 固定 3 列，每页 30 条可以整除 */
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
}
.record-card {
  position: relative;
  transition: all 0.2s ease;
  min-width: 220px;
  /* 重置 Element Plus 卡片内边距 */
  --el-card-padding: 0;
}
.record-card:hover {
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
  cursor: pointer;
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
.name-div {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.name-div .name {
  font-weight: 600;
  font-size: 16px;
}
.name-div .sid {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.size {
  color: var(--el-color-primary);
  font-size: 24px;
  font-weight: 700;
}
.size small {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: 2px;
}
.time-line {
  color: var(--el-text-color-regular);
  font-size: 12px;
  margin-top: 8px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
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
  position: relative;
}
.dialog-media .preview-img {
  width: 100%;
  height: 100%;
}
.dialog-media .layer {
  position: absolute;
  inset: 0;
}
.dialog-meta {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
}
.meta-info {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.meta-div .label {
  color: var(--el-text-color-placeholder);
  font-weight: 600;
}
.meta-div .value {
  color: var(--el-text-color-primary);
  font-size: var(--el-font-size-medium);
}
.meta-div .name-div {
  margin-top: 4px;
}
.meta-div .name {
  font-size: 18px;
}
.meta-div .sid {
  font-size: 12px;
}
.meta-ops {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
}
.btn-group .el-button,
.btn-group .el-link {
  margin: 0;
  width: 120px;
}
</style>
