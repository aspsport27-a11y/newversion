import { createApp } from 'vue'
import App from './App.vue'
import CoachSchedule from './CoachSchedule.vue'
import './style.css'

// Situs ini tanpa router (statis). Halaman jadwal pribadi coach dibedakan
// lewat query param `?coach=<token>` — sengaja query param, bukan path,
// supaya tak butuh konfigurasi SPA-fallback di nginx.
const token = new URLSearchParams(window.location.search).get('coach')

if (token) {
  createApp(CoachSchedule, { token }).mount('#app')
} else {
  createApp(App).mount('#app')
}
