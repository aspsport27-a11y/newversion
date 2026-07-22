import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { guestOnly: true } },
  { path: '/', name: 'pos', component: () => import('../views/PosView.vue'), meta: { requiresAuth: true } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  const token = localStorage.getItem('pos_token')
  if (to.meta.requiresAuth && !token) return { name: 'login' }
  if (to.meta.guestOnly && token) return { name: 'pos' }
  return true
})

// lihat frontend-admin: chunk lama yg dihapus rsync --delete saat redeploy
// bisa gagal diam-diam di tab yg sudah lama terbuka → reload penuh utk pulih
router.onError((err, to) => {
  if (/Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed/i.test(err.message)) {
    window.location.href = to.fullPath
  }
})

export default router
