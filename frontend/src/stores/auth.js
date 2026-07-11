import { defineStore } from 'pinia'
import client from '../api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: JSON.parse(localStorage.getItem('user') || 'null'),
    accessToken: localStorage.getItem('access_token') || null,
  }),
  getters: {
    isAuthenticated: (s) => !!s.accessToken,
    roleLabel: (s) => {
      const map = {
        admin: 'Administrator',
        head_office: 'Head Office',
        manager_unit: 'Manager Unit',
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
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      localStorage.setItem('user', JSON.stringify(data.user))
    },
    async fetchMe() {
      const { data } = await client.get('/auth/me')
      this.user = data.user
      localStorage.setItem('user', JSON.stringify(data.user))
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
    },
  },
})
