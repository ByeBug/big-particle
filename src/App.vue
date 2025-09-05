<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import GlobalAside from './components/GlobalAside.vue'
import GlobalHeader from './components/GlobalHeader.vue'

const router = useRouter()

// 计算需要 keep-alive 的组件名称
const keepAliveNames = computed(() => {
  return router
    .getRoutes()
    .filter((route) => route.meta?.keepAlive === true && !!route.meta?.keepAliveName)
    .map((route) => route.meta!.keepAliveName as string)
})
</script>

<template>
  <el-container class="app-container">
    <el-header>
      <GlobalHeader />
    </el-header>

    <el-main>
      <GlobalAside />
      <div class="main">
        <RouterView v-slot="{ Component }">
          <KeepAlive :include="keepAliveNames">
            <component :is="Component" />
          </KeepAlive>
        </RouterView>
      </div>
    </el-main>
  </el-container>
</template>

<style scoped>
.app-container {
  height: 100vh;
}
.el-main {
  display: flex;
  padding: 0;
}
.main {
  background-color: var(--el-bg-color-page);
  padding: var(--el-main-padding);
  flex: 1;
  overflow: auto;
}
</style>
