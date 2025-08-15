<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { computed } from 'vue'

const router = useRouter()
const route = useRoute()

// 从路由配置中获取菜单项
const menuItems = computed(() => {
  return router
    .getRoutes()
    .filter((route) => {
      // 过滤条件：
      // 1. 有标题
      // 2. 不隐藏
      // 3. 不是动态路由（包含参数的路由）
      // 4. 不是根路由重定向
      return (
        route.meta?.title && !route.meta?.hidden && !route.path.includes(':') && route.path !== '/'
      )
    })
    .map((route) => ({
      name: route.name,
      path: route.path,
      title: route.meta?.title,
      icon: route.meta?.icon,
      requiresAuth: route.meta?.requiresAuth,
      roles: route.meta?.roles,
      order: (route.meta?.order as number) || 999, // 直接在这里获取 order
    }))
    .sort((a, b) => (a.order as number) - (b.order as number)) // 使用已经提取的 order 字段排序
})

// 根据用户权限过滤菜单项
const visibleMenuItems = computed(() => {
  // 这里可以根据用户权限进一步过滤
  // const userRole = getUserRole() // 假设有获取用户角色的方法

  return menuItems.value.filter((item) => {
    // 如果不需要认证，直接显示
    if (!item.requiresAuth) return true

    // 这里添加具体的权限检查逻辑
    // if (!isLoggedIn()) return false
    // if (item.roles && !item.roles.includes(userRole)) return false

    return true // 临时返回 true，实际项目中需要实现权限检查
  })
})

const activeMenu = computed(() => route.name as string)

const handleMenuClick = (routeName: string) => {
  router.push({ name: routeName })
}
</script>

<template>
  <div class="aside">
    <el-scrollbar>
      <el-menu :default-active="activeMenu" @select="handleMenuClick">
        <el-menu-item v-for="item in visibleMenuItems" :key="item.name" :index="item.name">
          <el-icon v-if="item.icon">
            <component :is="item.icon" />
          </el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-menu>
    </el-scrollbar>
  </div>
</template>

<style scoped>
.aside {
  min-width: 200px;
}
.el-menu {
  min-height: calc(100vh - 60px);
}
</style>
