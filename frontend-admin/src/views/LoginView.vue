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
  <div class="min-h-screen flex bg-white">
    <!-- ===== Panel brand (kiri, desktop) ===== -->
    <div class="hidden lg:flex lg:w-[46%] bg-gradient-to-br from-brand-700 to-brand-900 text-white flex-col justify-between p-12 relative overflow-hidden">
      <div class="absolute -top-24 -right-24 w-72 h-72 rounded-full bg-white/5"></div>
      <div class="absolute -bottom-32 -left-16 w-96 h-96 rounded-full bg-white/5"></div>

      <div class="relative">
        <img src="/asp-logo.png" alt="ASP Sports" class="h-9" style="filter: brightness(0) invert(1)" />
      </div>

      <div class="relative">
        <h1 class="text-4xl font-semibold leading-tight mb-4">Sistem Manajemen<br />Venue Terintegrasi</h1>
        <p class="text-brand-100 text-base leading-relaxed max-w-sm mb-8">
          Kelola booking, kasir, keuangan, dan operasional seluruh venue dalam satu platform.
        </p>
        <ul class="space-y-3 text-brand-50 text-sm">
          <li class="flex items-center gap-3">
            <span class="h-6 w-6 rounded-full bg-white/15 flex items-center justify-center text-xs">✓</span>
            POS kasir &amp; booking real-time
          </li>
          <li class="flex items-center gap-3">
            <span class="h-6 w-6 rounded-full bg-white/15 flex items-center justify-center text-xs">✓</span>
            Laporan keuangan &amp; kas terpusat
          </li>
          <li class="flex items-center gap-3">
            <span class="h-6 w-6 rounded-full bg-white/15 flex items-center justify-center text-xs">✓</span>
            Kontrol multi-venue &amp; hak akses
          </li>
        </ul>
      </div>

      <p class="relative text-xs text-brand-200">© {{ new Date().getFullYear() }} ASP Sports · Venue Management System</p>
    </div>

    <!-- ===== Panel form (kanan) ===== -->
    <div class="flex-1 flex items-center justify-center px-6 py-12">
      <div class="w-full max-w-sm">
        <!-- logo mobile -->
        <div class="lg:hidden mb-10 text-center">
          <div class="inline-flex items-center justify-center h-14 w-14 rounded-2xl bg-brand-600 mb-3">
            <img src="/asp-logo.png" alt="ASP Sports" class="h-7" style="filter: brightness(0) invert(1)" />
          </div>
          <p class="text-slate-400 text-sm">Venue Management System</p>
        </div>

        <div class="mb-8">
          <h2 class="text-2xl font-semibold text-slate-800">Selamat datang 👋</h2>
          <p class="text-slate-500 text-sm mt-1">Masuk untuk melanjutkan ke portal.</p>
        </div>

        <form @submit.prevent="submit" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-slate-600 mb-1.5">Username atau Email</label>
            <div class="relative">
              <span class="absolute inset-y-0 left-0 pl-3.5 flex items-center text-slate-400">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              </span>
              <input v-model="username" type="text" autocomplete="username" required placeholder="admin"
                class="w-full rounded-xl border border-slate-300 bg-slate-50 focus:bg-white pl-11 pr-3 py-3 text-sm outline-none focus:border-brand-500 focus:ring-4 focus:ring-brand-100 transition" />
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-slate-600 mb-1.5">Password</label>
            <div class="relative">
              <span class="absolute inset-y-0 left-0 pl-3.5 flex items-center text-slate-400">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              </span>
              <input v-model="password" :type="showPw ? 'text' : 'password'" autocomplete="current-password" required placeholder="••••••••"
                class="w-full rounded-xl border border-slate-300 bg-slate-50 focus:bg-white pl-11 pr-11 py-3 text-sm outline-none focus:border-brand-500 focus:ring-4 focus:ring-brand-100 transition" />
              <button type="button" @click="showPw = !showPw" tabindex="-1"
                class="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-600 transition" :aria-label="showPw ? 'Sembunyikan password' : 'Tampilkan password'">
                <svg v-if="showPw" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
            </div>
          </div>

          <p v-if="error" class="text-sm text-red-600 bg-red-50 border border-red-100 rounded-xl px-3.5 py-2.5">{{ error }}</p>

          <button type="submit" :disabled="loading"
            class="w-full bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white font-medium rounded-xl py-3 transition flex items-center justify-center gap-2">
            <span>{{ loading ? 'Memproses…' : 'Masuk' }}</span>
            <svg v-if="!loading" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </button>
        </form>

        <p class="text-center text-slate-400 text-xs mt-8">portal.aspsports.id</p>
      </div>
    </div>
  </div>
</template>
