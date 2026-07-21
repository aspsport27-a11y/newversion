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
      { path: 'areas', name: 'areas', component: () => import('../views/AreasView.vue') },
      { path: 'employees', name: 'employees', component: () => import('../views/EmployeesView.vue') },
      { path: 'attendance', name: 'attendance', component: () => import('../views/AttendanceView.vue') },
      { path: 'operational', name: 'operational', component: () => import('../views/OperationalView.vue') },
      { path: 'procurement', name: 'procurement', component: () => import('../views/ProcurementView.vue') },
      { path: 'payroll', name: 'payroll', component: () => import('../views/PayrollView.vue') },
      { path: 'treasury', name: 'treasury', component: () => import('../views/TreasuryView.vue') },
      { path: 'products', name: 'products', component: () => import('../views/ProductsView.vue') },
      { path: 'promos', name: 'promos', component: () => import('../views/PromosView.vue') },
      { path: 'facilities', name: 'facilities', component: () => import('../views/FacilitiesView.vue') },
      { path: 'bookings', name: 'bookings', component: () => import('../views/BookingsView.vue') },
      { path: 'reports', name: 'reports', component: () => import('../views/ReportsView.vue') },
      { path: 'transactions', name: 'transactions', component: () => import('../views/TransactionsView.vue') },
      { path: 'financial', name: 'financial', component: () => import('../views/FinancialView.vue') },
      { path: 'management-report', name: 'management-report', component: () => import('../views/ManagementReportView.vue') },
      { path: 'permissions', name: 'permissions', component: () => import('../views/PermissionsView.vue') },
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
  // admin_unit tidak punya menu Dashboard → arahkan ke Operasional
  if (to.name === 'dashboard') {
    try {
      const u = JSON.parse(localStorage.getItem('user') || 'null')
      if (u?.role === 'admin_unit') return { name: 'operational' }
    } catch { /* ignore */ }
  }
  return true
})

export default router
