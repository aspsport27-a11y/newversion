<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const showPw = ref(false)
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    router.push({ name: 'dashboard' })
  } catch (e) {
    error.value = e?.response?.data?.message || 'Login gagal. Periksa username/password.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="relative min-h-screen flex items-center justify-center px-4 py-12 overflow-hidden bg-gradient-to-br from-brand-700 via-brand-800 to-brand-900">
    <!-- ===== Doodle olahraga (latar) ===== -->
    <div class="pointer-events-none absolute inset-0 text-white/[0.07]" aria-hidden="true">
      <!-- bola sepak -->
      <svg class="doodle absolute top-[8%] left-[6%] w-24 h-24 -rotate-12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <circle cx="12" cy="12" r="9" /><path d="M12 7l3 2-1 3.5h-4L9 9z" /><path d="M12 7V3.5M15 9l3-1.5M14 12.5l2.5 2.5M10 12.5L7.5 15M9 9L6 7.5" />
      </svg>
      <!-- bola basket -->
      <svg class="doodle absolute top-[14%] right-[8%] w-28 h-28 rotate-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <circle cx="12" cy="12" r="9" /><path d="M12 3v18M3 12h18M5.6 5.6C8 8 8 16 5.6 18.4M18.4 5.6C16 8 16 16 18.4 18.4" />
      </svg>
      <!-- kok bulutangkis -->
      <svg class="doodle absolute top-[44%] left-[10%] w-20 h-20 rotate-12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <circle cx="12" cy="18" r="3" /><path d="M12 15l-4-9M12 15l4-9M12 15l-1.5-9.5M12 15l1.5-9.5M8 6l8 0" />
      </svg>
      <!-- stik / raket -->
      <svg class="doodle absolute bottom-[12%] right-[12%] w-24 h-24 -rotate-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <ellipse cx="9" cy="9" rx="5" ry="6" transform="rotate(-30 9 9)" /><path d="M12.5 12.5L20 20" /><path d="M6.5 6.5l5 5M9 5l3 6M5 9l6 3" />
      </svg>
      <!-- peluit -->
      <svg class="doodle absolute bottom-[16%] left-[16%] w-16 h-16 rotate-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <path d="M3 10h11l4 2v3a4 4 0 0 1-8 0H3z" /><circle cx="9" cy="14" r="2" /><path d="M14 8V5" />
      </svg>
      <!-- stopwatch -->
      <svg class="doodle absolute top-[62%] right-[22%] w-16 h-16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <circle cx="12" cy="13" r="7" /><path d="M12 13V9M10 3h4M18 6l1.5-1.5" />
      </svg>
      <!-- controller (esport) -->
      <svg class="doodle absolute top-[30%] right-[38%] w-20 h-20 -rotate-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <path d="M7 8h10a4 4 0 0 1 4 4l-1 4a2.5 2.5 0 0 1-4.3 1L14 15h-4l-1.7 2A2.5 2.5 0 0 1 4 16l-1-4a4 4 0 0 1 4-4z" /><path d="M7.5 11v2M6.5 12h2M15.5 11.5h.01M17 13h.01" />
      </svg>
      <!-- gawang / lapangan garis -->
      <svg class="doodle absolute top-[76%] left-[40%] w-24 h-24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <path d="M2 20h20M6 20V8h12v12M6 8l3-3h6l3 3M9 20v-9h6v9" />
      </svg>
      <!-- trofi -->
      <svg class="doodle absolute top-[6%] left-[46%] w-16 h-16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <path d="M8 4h8v4a4 4 0 0 1-8 0zM8 5H5v2a3 3 0 0 0 3 3M16 5h3v2a3 3 0 0 1-3 3M12 12v4M9 20h6M10 16h4v4h-4z" />
      </svg>
      <!-- ombak (waterpark) -->
      <svg class="doodle absolute bottom-[6%] right-[42%] w-28 h-16" viewBox="0 0 40 12" fill="none" stroke="currentColor" stroke-width="1.2">
        <path d="M0 6c3-4 6-4 9 0s6 4 9 0 6-4 9 0 6 4 9 0" /><path d="M0 10c3-4 6-4 9 0s6 4 9 0 6-4 9 0 6 4 9 0" />
      </svg>
    </div>

    <!-- ===== Card glassmorphism ===== -->
    <div class="relative w-full max-w-sm rounded-3xl border border-white/20 bg-white/10 backdrop-blur-2xl shadow-2xl px-8 py-10">
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center h-16 w-16 rounded-2xl bg-white/15 border border-white/20 mb-4">
          <img src="/asp-logo.png" alt="ASP Sports" class="h-8" style="filter: brightness(0) invert(1)" />
        </div>
        <h1 class="text-xl font-semibold text-white">Selamat datang</h1>
        <p class="text-sm text-white/60 mt-1">Masuk ke ASP Sports Venue Management</p>
      </div>

      <form @submit.prevent="submit" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-white/80 mb-1.5">Username atau Email</label>
          <div class="relative">
            <span class="absolute inset-y-0 left-0 pl-3.5 flex items-center text-white/50">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            </span>
            <input v-model="username" type="text" autocomplete="username" required placeholder="admin"
              class="w-full rounded-xl bg-white/10 border border-white/20 pl-11 pr-3 py-3 text-sm text-white placeholder-white/40 outline-none focus:border-white/50 focus:ring-4 focus:ring-white/10 transition" />
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-white/80 mb-1.5">Password</label>
          <div class="relative">
            <span class="absolute inset-y-0 left-0 pl-3.5 flex items-center text-white/50">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            </span>
            <input v-model="password" :type="showPw ? 'text' : 'password'" autocomplete="current-password" required placeholder="••••••••"
              class="w-full rounded-xl bg-white/10 border border-white/20 pl-11 pr-11 py-3 text-sm text-white placeholder-white/40 outline-none focus:border-white/50 focus:ring-4 focus:ring-white/10 transition" />
            <button type="button" @click="showPw = !showPw" tabindex="-1"
              class="absolute inset-y-0 right-0 pr-3.5 flex items-center text-white/50 hover:text-white transition" :aria-label="showPw ? 'Sembunyikan password' : 'Tampilkan password'">
              <svg v-if="showPw" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            </button>
          </div>
        </div>

        <p v-if="error" class="text-sm text-red-50 bg-red-500/25 border border-red-300/30 rounded-xl px-3.5 py-2.5">{{ error }}</p>

        <button type="submit" :disabled="loading"
          class="w-full bg-white text-brand-700 hover:bg-brand-50 disabled:opacity-60 font-semibold rounded-xl py-3 transition flex items-center justify-center gap-2 shadow-lg">
          <span>{{ loading ? 'Memproses…' : 'Masuk' }}</span>
          <svg v-if="!loading" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
        </button>
      </form>

      <p class="text-center text-white/50 text-xs mt-8">© {{ new Date().getFullYear() }} ASP Sports · portal.aspsports.id</p>
    </div>
  </div>
</template>

<style scoped>
/* animasi mengambang halus untuk doodle — pakai properti `translate` (bukan
   `transform`) supaya tidak menimpa rotasi Tailwind pada tiap doodle */
@keyframes float-doodle {
  0%, 100% { translate: 0 0; }
  50%      { translate: 0 -14px; }
}
.doodle {
  animation: float-doodle 7s ease-in-out infinite;
  will-change: translate;
}
/* durasi & delay bervariasi supaya gerakannya tidak seragam */
.doodle:nth-of-type(1) { animation-duration: 8s;  animation-delay: 0s; }
.doodle:nth-of-type(2) { animation-duration: 10s; animation-delay: -3s; }
.doodle:nth-of-type(3) { animation-duration: 7s;  animation-delay: -1.5s; }
.doodle:nth-of-type(4) { animation-duration: 9s;  animation-delay: -4s; }
.doodle:nth-of-type(5) { animation-duration: 6.5s; animation-delay: -2s; }
.doodle:nth-of-type(6) { animation-duration: 11s; animation-delay: -5s; }
.doodle:nth-of-type(7) { animation-duration: 8.5s; animation-delay: -1s; }
.doodle:nth-of-type(8) { animation-duration: 7.5s; animation-delay: -3.5s; }
.doodle:nth-of-type(9) { animation-duration: 9.5s; animation-delay: -2.5s; }
.doodle:nth-of-type(10){ animation-duration: 6s;  animation-delay: -4.5s; }

@media (prefers-reduced-motion: reduce) {
  .doodle { animation: none; }
}
</style>
