<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { listVideoStreams, updateVideoStream, type VideoStreamItem } from '@/services/videostreams'

const loading = ref(true)
const page = ref(1)
const pageSize = 30
const total = ref(0)
const rows = ref<VideoStreamItem[]>([])

const fetchList = async () => {
  loading.value = true
  try {
    const res = await listVideoStreams({ page: page.value })
    total.value = res.count
    rows.value = res.results
  } finally {
    loading.value = false
  }
}

const toggleEnabled = async (row: VideoStreamItem) => {
  const prev = row.enabled
  const next = !prev
  row.enabled = next
  try {
    const updated = await updateVideoStream(row.id, { enabled: next })
    // 用返回值更新当前行
    Object.assign(row, updated)
  } catch {
    row.enabled = prev
    ElMessage.error('更新失败，请重试')
    // 兜底：刷新当前页数据，确保与服务端一致
    await fetchList()
  }
}

const formatResolution = (w?: number | null, h?: number | null) => (w && h ? `${w}×${h}` : '-')

let pollTimer: number | null = null
const startPolling = async () => {
  await fetchList()
  pollTimer = window.setTimeout(startPolling, 10000)
}

onMounted(() => {
  startPolling()
})

onUnmounted(() => {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
})
</script>

<template>
  <div class="stream-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>流列表</span>
        </div>
      </template>

      <el-table :data="rows" v-loading="loading">
        <el-table-column label="名称 / ID" min-width="180">
          <template #default="{ row }">
            <div class="name-id">
              <span class="name">{{ row.name }}</span>
              <span class="sid">ID: {{ row.id }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="IP" min-width="140">
          <template #default="{ row }">{{ row.ip || '-' }}</template>
        </el-table-column>
        <el-table-column label="地址" show-overflow-tooltip min-width="260">
          <template #default="{ row }">
            <span class="address" :title="row.address">{{ row.address }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分辨率" min-width="120">
          <template #default="{ row }">{{ formatResolution(row.width, row.height) }}</template>
        </el-table-column>
        <el-table-column label="帧率" min-width="90">
          <template #default="{ row }">{{ row.fps ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" align="center" min-width="90">
          <template #default="{ row }">
            <el-tooltip
              :disabled="!row.status_message"
              :content="row.status_message"
              placement="top"
            >
              <el-tag
                :type="
                  row.status === 'abnormal'
                    ? 'danger'
                    : row.status === 'disabled'
                      ? 'info'
                      : 'success'
                "
              >
                {{
                  row.status === 'abnormal' ? '异常' : row.status === 'disabled' ? '未启用' : '正常'
                }}
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="180">
          <template #default="{ row }">{{
            dayjs(row.created_at).format('YYYY-MM-DD HH:mm:ss')
          }}</template>
        </el-table-column>
        <el-table-column label="启用" min-width="100" align="center">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" @change="() => toggleEnabled(row)" />
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          background
          layout="slot, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          v-model:current-page="page"
          @current-change="fetchList"
        >
          <span>共 {{ total.toLocaleString() }} 条</span>
        </el-pagination>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.name-id {
  display: flex;
  flex-direction: column;
}
.name-id .name {
  font-weight: 600;
}
.name-id .sid {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.address {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:deep(.el-switch__core),
:deep(.el-switch__core .el-switch__action) {
  border-radius: 0;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
