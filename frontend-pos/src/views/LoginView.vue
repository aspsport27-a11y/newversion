<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { usePosStore } from '../stores/pos'

const router = useRouter()
const pos = usePosStore()

const terminalCode = ref(localStorage.getItem('pos_terminal_code') || '')
const username = ref('')
const pin = ref('')
const error = ref('')
const loading = ref(false)

onMounted(() => {
  // kalau terminal sudah pernah diset, langsung fokus ke username
})

function tap(d) {
  if (pin.value.length < 8) pin.value += d
}
function backspace() {
  pin.value = pin.value.slice(0, -1)
}

async function submit() {
  if (!terminalCode.value || !username.value || !pin.value) {
    error.value = 'Terminal, username, dan PIN wajib diisi.'
    return
  }
  error.value = ''
  loading.value = true
  try {
    await pos.login(terminalCode.value.trim(), username.value.trim(), pin.value)
    localStorage.setItem('pos_terminal_code', terminalCode.value.trim())
    router.push({ name: 'pos' })
  } catch (e) {
    error.value = e?.response?.data?.message || 'Login gagal.'
    pin.value = ''
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-full flex items-center justify-center p-4 bg-gradient-to-br from-brand-700 to-brand-900">
    <div class="w-full max-w-sm bg-white rounded-2xl shadow-xl p-6">
      <div class="text-center mb-5">
        <div class="text-3xl mb-1">🏟️</div>
        <h1 class="text-xl font-bold text-slate-800">ASP Sport POS</h1>
        <p class="text-xs text-slate-400">Login Kasir</p>
      </div>

      <div class="space-y-3">
        <input
          v-model="terminalCode"
          placeholder="Kode Terminal (mis. T-V001-01)"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-100 outline-none"
        />
        <input
          v-model="username"
          placeholder="Username kasir"
          autocomplete="username"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-100 outline-none"
        />

        <div class="flex justify-center gap-2 py-1">
          <span
            v-for="n in 4"
            :key="n"
            class="h-3 w-3 rounded-full"
            :class="pin.length >= n ? 'bg-brand-600' : 'bg-slate-200'"
          />
        </div>

        <div class="grid grid-cols-3 gap-2">
          <button
            v-for="d in ['1','2','3','4','5','6','7','8','9']"
            :key="d"
            @click="tap(d)"
            class="py-3 rounded-lg bg-slate-100 hover:bg-slate-200 text-xl font-semibold text-slate-700 active:scale-95 transition"
          >
            {{ d }}
          </button>
          <button @click="backspace" class="py-3 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-500 active:scale-95">⌫</button>
          <button @click="tap('0')" class="py-3 rounded-lg bg-slate-100 hover:bg-slate-200 text-xl font-semibold text-slate-700 active:scale-95">0</button>
          <button
            @click="submit"
            :disabled="loading"
            class="py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-semibold active:scale-95 disabled:opacity-60"
          >
            {{ loading ? '…' : 'OK' }}
          </button>
        </div>

        <p v-if="error" class="text-sm text-center text-red-600 bg-red-50 rounded-lg px-3 py-2">{{ error }}</p>
      </div>
    </div>
  </div>
</template>
