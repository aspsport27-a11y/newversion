import { defineStore } from 'pinia'
import client from '../api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: JSON.parse(localStorage.getItem('user') || 'null'),
    accessToken: localStorage.getItem('access_token') || null,
    permissions: JSON.parse(localStorage.getItem('permissions') || '[]'),
  }),
  getters: {
    isAuthenticated: (s) => !!s.accessToken,
    // admin = superuser (selalu true); lainnya cek daftar izin
    hasPerm: (s) => (code) => s.user?.role === 'admin' || s.permissions.includes(code),
    roleLabel: (s) => {
      const map = {
        admin: 'Administrator',
        head_office: 'Head Office',
        manager_unit: 'Manager Unit',
        admin_unit: 'Admin Unit (Area)',
        staff: 'Staff / Kasir',
      }
      return s.user ? map[s.user.role] || s.user.role : ''
    },
  },
  actions: {
    async login(username, password) {
      const { data } = await client.post('/auth/login', { username, password })
      this.accessToken = data.access_token
      this.user = data.user
      this.permissions = data.permissions || []
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      localStorage.setItem('user', JSON.stringify(data.user))
      localStorage.setItem('permissions', JSON.stringify(this.permissions))
    },
    async fetchMe() {
      const { data } = await client.get('/auth/me')
      this.user = data.user
      this.permissions = data.permissions || []
      localStorage.setItem('user', JSON.stringify(data.user))
      localStorage.setItem('permissions', JSON.stringify(this.permissions))
    },
    async logout() {
      try {
        await client.post('/auth/logout')
      } catch (_) {
        /* abaikan error jaringan saat logout */
      }
      this.$reset()
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user')
      localStorage.removeItem('permissions')
    },
  },
})
