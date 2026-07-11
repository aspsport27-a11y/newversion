import axios from 'axios'

const client = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE || '/api') + '/pos',
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('pos_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response && err.response.status === 401) {
      localStorage.removeItem('pos_token')
      if (window.location.pathname !== '/login') window.location.replace('/login')
    }
    return Promise.reject(err)
  },
)

export default client
