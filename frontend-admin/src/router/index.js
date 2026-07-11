import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/',
    component: () => import('../layouts/DashboardLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
      { path: 'venues', name: 'venues', component: () => import('../views/VenuesView.vue') },
      { path: 'products', name: 'products', component: () => import('../views/ProductsView.vue') },
      { path: 'facilities', name: 'facilities', component: () => import('../views/FacilitiesView.vue') },
      { path: 'bookings', name: 'bookings', component: () => import('../views/BookingsView.vue') },
      { path: 'reports', name: 'reports', component: () => import('../views/ReportsView.vue') },
      { path: 'setup', name: 'setup', component: () => import('../views/SetupView.vue') },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  if (to.meta.requiresAuth && !token) return { name: 'login' }
  if (to.meta.guestOnly && token) return { name: 'dashboard' }
  return true
})

export default router
