<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    router.push({ name: 'dashboard' })
  } catch (e) {
    error.value =
      e?.response?.data?.message || 'Login gagal. Periksa username/password.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-full flex items-center justify-center px-4 py-12 bg-gradient-to-br from-brand-700 to-brand-900">
    <div class="w-full max-w-md">
      <div class="text-center mb-8">
        <img src="/asp-logo.png" alt="ASP Sports" class="h-16 mx-auto mb-3" style="filter: brightness(0) invert(1)" />
        <p class="text-brand-100 text-sm">Venue Management System</p>
      </div>

      <div class="bg-white rounded-2xl shadow-xl p-8">
        <h2 class="text-lg font-semibold text-slate-800 mb-6">Masuk ke akun Anda</h2>

        <form @submit.prevent="submit" class="space-y-5">
          <div>
            <label class="block text-sm font-medium text-slate-600 mb-1">Username atau Email</label>
            <input
              v-model="username"
              type="text"
              autocomplete="username"
              required
              class="w-full rounded-lg border border-slate-300 px-3 py-2.5 focus:border-brand-500 focus:ring-2 focus:ring-brand-100 outline-none transition"
              placeholder="admin"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-slate-600 mb-1">Password</label>
            <input
              v-model="password"
              type="password"
              autocomplete="current-password"
              required
              class="w-full rounded-lg border border-slate-300 px-3 py-2.5 focus:border-brand-500 focus:ring-2 focus:ring-brand-100 outline-none transition"
              placeholder="••••••••"
            />
          </div>

          <p v-if="error" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
            {{ error }}
          </p>

          <button
            type="submit"
            :disabled="loading"
            class="w-full bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white font-medium rounded-lg py-2.5 transition"
          >
            {{ loading ? 'Memproses…' : 'Masuk' }}
          </button>
        </form>
      </div>

      <p class="text-center text-brand-100 text-xs mt-6">
        © {{ new Date().getFullYear() }} ASP Sports · portal.aspsports.id
      </p>
    </div>
  </div>
</template>
