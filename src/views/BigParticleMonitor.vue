<script setup lang="ts">
import { ref, onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'

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

// 模拟实时数据更新
const updateData = () => {
  monitorData.value = {
    particleCount: Math.floor(Math.random() * 1000),
    temperature: (Math.random() * 100).toFixed(1),
    pressure: (Math.random() * 10).toFixed(2),
    flowRate: (Math.random() * 50).toFixed(1),
  }
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
