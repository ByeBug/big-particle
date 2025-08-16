<script setup lang="ts">
import { ref, onMounted } from 'vue'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import { listBigParticleRecords, type BigParticleRecordItem } from '@/services/bigParticleRecords'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const loading = ref(false)
const page = ref(1)
const pageSize = 30
const total = ref(0)
const records = ref<BigParticleRecordItem[]>([])

const fetchRecords = async () => {
  loading.value = true
  try {
    const res = await listBigParticleRecords({ page: page.value })
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

onMounted(fetchRecords)

const resolveImageUrl = (path: string) => {
  if (!path) return ''
  // TODO 返回临时拼接的 url
  return `http://192.168.3.13/storage/big-particle-data${path}`
}
</script>

<template>
  <div class="record-page">
    <div class="record-grid">
      <div v-for="item in records" :key="item.id" class="record-item">
        <el-card shadow="never" class="record-card">
          <div class="card-top">
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
  </div>
</template>

<style scoped>
.record-page {
  padding-bottom: 20px;
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
  align-items: baseline;
  gap: 8px;
}
.name-div {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.name-div .name {
  font-weight: 600;
}
.name-div .sid {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.title-line .size {
  color: var(--el-color-primary);
  font-size: 18px;
  font-weight: 700;
}
.title-line .size small {
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
</style>
