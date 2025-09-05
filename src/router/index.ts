import { createRouter, createWebHistory } from 'vue-router'
// 路由级代码分割：动态导入各页面

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/monitor',
      alias: '/', // 设置别名
      name: 'monitor',
      component: () => import('@/views/BigParticleMonitor.vue'),
      meta: {
        title: '大颗粒监控',
        icon: 'Monitor',
        requiresAuth: false,
        keepAlive: true,
        keepAliveName: 'BigParticleMonitor', // KeepAlive 组件名
        order: 1, // 菜单排序
        group: 'monitor', // 菜单分组
      },
    },
    {
      path: '/record',
      name: 'record',
      component: () => import('@/views/BigParticleRecord.vue'),
      meta: {
        title: '大颗粒记录',
        icon: 'Document',
        requiresAuth: false,
        keepAlive: false,
        keepAliveName: 'BigParticleRecord',
        order: 2,
      },
    },
    {
      path: '/streams',
      name: 'streams',
      component: () => import('@/views/StreamManagement.vue'),
      meta: {
        title: '流管理',
        icon: 'Connection',
        requiresAuth: true,
        roles: ['admin'],
        keepAliveName: 'StreamManagement',
        order: 3,
      },
    },
    {
      path: '/config',
      name: 'config',
      component: () => import('@/views/SystemConfig.vue'),
      meta: {
        title: '系统配置',
        icon: 'Setting',
        requiresAuth: true,
        roles: ['admin'],
        hidden: false,
        keepAliveName: 'SystemConfig',
        order: 4,
      },
    },
    // 404 匹配所有未定义的路径
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

// 全局路由守卫 - 设置页面标题
router.beforeEach((to, from, next) => {
  // 设置浏览器标签页标题
  if (to.meta?.title) {
    document.title = `${to.meta.title} - 大颗粒监控系统`
  } else {
    document.title = '大颗粒监控系统'
  }

  next()
})

export default router
