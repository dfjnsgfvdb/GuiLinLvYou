const childrenRoutes: Array<RouteRecordRaw> = [
  {
    path: 'overview',
    name: 'TourismOverview',
    component: () => import('@/views/tourism/Overview.vue'),
    meta: { requiresAuth: true, title: '舆情总览' },
  },
  {
    path: 'chat',
    name: 'ChatIndex',
    component: () => import('@/views/chat.vue'),
    meta: { requiresAuth: true, title: '智能研判' },
  },
  {
    path: 'events',
    name: 'TourismEvents',
    component: () => import('@/views/tourism/EventList.vue'),
    meta: { requiresAuth: true, title: '事件监测' },
  },
  {
    path: 'graph',
    name: 'TourismGraph',
    component: () => import('@/views/tourism/GraphView.vue'),
    meta: { requiresAuth: true, title: '知识图谱' },
  },
  {
    path: 'pipeline',
    name: 'TourismPipeline',
    component: () => import('@/views/tourism/DataPipeline.vue'),
    meta: { requiresAuth: true, title: '数据管道' },
  },
  {
    path: 'system',
    name: 'TourismSystem',
    component: () => import('@/views/tourism/SystemSettings.vue'),
    meta: { requiresAuth: true, title: '系统状态' },
  },
]

export default childrenRoutes
