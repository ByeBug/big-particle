import { createRouter, createWebHistory } from 'vue-router'
import BigParticleMonitor from '@/views/BigParticleMonitor.vue'
import BigParticleRecord from '@/views/BigParticleRecord.vue'
import StreamManagement from '@/views/StreamManagement.vue'
import SystemConfig from '@/views/SystemConfig.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/monitor',
      alias: '/', // 设置别名
      name: 'monitor',
      component: BigParticleMonitor,
      meta: {
        title: '大颗粒监控',
        icon: 'Monitor',
        requiresAuth: false,
        keepAlive: true,
        order: 1, // 菜单排序
        group: 'monitor', // 菜单分组
      },
    },
    {
      path: '/record',
      name: 'record',
      component: BigParticleRecord,
      meta: {
        title: '大颗粒记录',
        icon: 'Document',
        requiresAuth: false,
        keepAlive: false,
        order: 2,
      },
    },
    {
      path: '/streams',
      name: 'streams',
      component: StreamManagement,
      meta: {
        title: '流管理',
        icon: 'Connection',
        requiresAuth: true,
        roles: ['admin'],
        order: 3,
      },
    },
    {
      path: '/config',
      name: 'config',
      component: SystemConfig,
      meta: {
        title: '系统配置',
        icon: 'Setting',
        requiresAuth: true,
        roles: ['admin'],
        hidden: false,
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
