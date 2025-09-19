<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getActiveBigParticleAlgorithmConfig,
  updateSystemConfig,
  type SystemConfigItem,
} from '@/services/systemConfigs'

interface AlarmRow {
  size_level: number | null
  warning_count: number | null
  warning_percentage: number | null
  error_count: number | null
  error_percentage: number | null
}

interface BigParticleConfigForm {
  threshold: number | null
  alarm_threshold: AlarmRow[]
}

const loading = ref(true)
const saving = ref(false)
const configItem = ref<SystemConfigItem | null>(null)
const form = reactive<BigParticleConfigForm>({
  threshold: null,
  alarm_threshold: [
    {
      size_level: null,
      warning_count: null,
      warning_percentage: null,
      error_count: null,
      error_percentage: null,
    },
  ],
})

const canAddRow = () => form.alarm_threshold.length < 10
const canRemoveRow = () => form.alarm_threshold.length > 1

const addRow = () => {
  if (!canAddRow()) return
  form.alarm_threshold.push({
    size_level: null,
    warning_count: null,
    warning_percentage: null,
    error_count: null,
    error_percentage: null,
  })
}

const removeRow = (idx: number) => {
  if (!canRemoveRow()) return
  form.alarm_threshold.splice(idx, 1)
}

function normalizeRows(rows: AlarmRow[]): AlarmRow[] {
  const normalized = rows.map((r) => ({
    size_level: Number(r.size_level ?? 0),
    warning_count: r.warning_count ?? null,
    warning_percentage: r.warning_percentage ?? null,
    error_count: r.error_count ?? null,
    error_percentage: r.error_percentage ?? null,
  }))
  normalized.sort((a, b) => (a.size_level ?? 0) - (b.size_level ?? 0))
  return normalized
}

const loadData = async () => {
  loading.value = true
  try {
    const item = await getActiveBigParticleAlgorithmConfig()
    if (!item) {
      ElMessage.warning('未找到活跃的大颗粒配置，使用默认空白表单')
      return
    }
    configItem.value = item
    const cfg = item.config_data as { threshold: number; alarm_threshold: AlarmRow[] }
    form.threshold = cfg.threshold
    form.alarm_threshold = normalizeRows(cfg.alarm_threshold)
  } catch {
    ElMessage.error('加载配置失败')
  } finally {
    loading.value = false
  }
}

const validateForm = (): string | null => {
  if (form.threshold === null || isNaN(form.threshold)) return '请填写阈值'
  if (form.threshold < 0 || form.threshold > 1) return '阈值需在 0~1 之间'
  const rows = form.alarm_threshold
  if (rows.length < 1 || rows.length > 10) return '粒径阈值行数需要在 1~10 之间'
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i]
    if (r.size_level === null || isNaN(r.size_level)) return `第 ${i + 1} 行：请填写粒径等级`
    // 其余字段均为可选；若填写则需为非负数
    const nums: Array<[keyof AlarmRow, number | null]> = [
      ['warning_count', r.warning_count],
      ['error_count', r.error_count],
      ['warning_percentage', r.warning_percentage],
      ['error_percentage', r.error_percentage],
    ]
    for (const [key, val] of nums) {
      if (val !== null) {
        if (isNaN(val)) return `第 ${i + 1} 行：${key} 需为数字`
        if (val < 0) return `第 ${i + 1} 行：${key} 需为非负`
      }
    }
  }
  const levels = rows.map((r) => r.size_level)
  const uniq = new Set(levels)
  if (uniq.size !== levels.length) return '粒径等级不可重复'
  return null
}

const handleSubmit = async () => {
  const err = validateForm()
  if (err) {
    ElMessage.warning(err)
    return
  }
  if (!configItem.value) {
    ElMessage.error('未获取到配置，无法保存')
    return
  }
  saving.value = true
  try {
    const payload = {
      config_data: {
        threshold: form.threshold,
        alarm_threshold: form.alarm_threshold.map((r): Record<string, number> => {
          const row: Record<string, number> = {
            size_level: Number(r.size_level),
          }
          if (typeof r.warning_count === 'number') row.warning_count = r.warning_count
          if (typeof r.warning_percentage === 'number')
            row.warning_percentage = r.warning_percentage
          if (typeof r.error_count === 'number') row.error_count = r.error_count
          if (typeof r.error_percentage === 'number') row.error_percentage = r.error_percentage
          return row
        }),
      },
    }
    const updated = await updateSystemConfig(configItem.value.id, payload)
    configItem.value = updated
    // 用后端返回的数据刷新并按 size_level 排序表单行
    const cfg2 = updated.config_data as { threshold: number; alarm_threshold: AlarmRow[] }
    if (cfg2) {
      form.threshold = cfg2.threshold
      form.alarm_threshold = normalizeRows(cfg2.alarm_threshold)
    }
    ElMessage.success('配置已更新')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div class="syscfg-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>大颗粒配置</span>
          <div class="header-ops">
            <el-button type="primary" :loading="saving" @click="handleSubmit">保存</el-button>
          </div>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="6" :throttle="100" animated />
      <div v-else class="form-wrap">
        <el-form label-width="auto">
          <el-form-item label="阈值 (0~1)">
            <el-input-number v-model="form.threshold" :step="0.01" :min="0.5" :max="1" />
          </el-form-item>

          <el-form-item label="粒径告警阈值 (1~10 行)">
            <div class="rows">
              <div class="row header">
                <span class="th col">粒径等级 (mm)</span>
                <span class="th col">预警计数</span>
                <span class="th col">预警百分比(%)</span>
                <span class="th col">错误计数</span>
                <span class="th col">错误百分比(%)</span>
                <span class="th actions">操作</span>
              </div>
              <div v-for="(row, idx) in form.alarm_threshold" :key="idx" class="row">
                <el-input-number
                  v-model="row.size_level"
                  :min="0"
                  :step="1"
                  :controls="false"
                  placeholder="粒径等级"
                  class="col"
                />
                <el-input-number
                  v-model="row.warning_count"
                  :min="0"
                  :step="1"
                  :controls="false"
                  placeholder="预警计数"
                  class="col"
                />
                <el-input-number
                  v-model="row.warning_percentage"
                  :min="0"
                  :step="0.1"
                  :controls="false"
                  placeholder="预警百分比(%)"
                  class="col"
                />
                <el-input-number
                  v-model="row.error_count"
                  :min="0"
                  :step="1"
                  :controls="false"
                  placeholder="错误计数"
                  class="col"
                />
                <el-input-number
                  v-model="row.error_percentage"
                  :min="0"
                  :step="0.1"
                  :controls="false"
                  placeholder="错误百分比(%)"
                  class="col"
                />
                <el-button type="danger" text :disabled="!canRemoveRow()" @click="removeRow(idx)"
                  >移除</el-button
                >
              </div>
              <div class="row ops">
                <el-button type="primary" plain :disabled="!canAddRow()" @click="addRow"
                  >新增一行</el-button
                >
              </div>
            </div>
          </el-form-item>
        </el-form>
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
.rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.row {
  display: flex;
  gap: 10px;
  align-items: center;
}
.row.header {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: 600;
}
.row.header .th {
  text-align: center;
}
.row .actions {
  flex: 1;
  text-align: center;
}
.row .col {
  width: 160px;
}
.row.ops {
  justify-content: flex-start;
}
</style>
