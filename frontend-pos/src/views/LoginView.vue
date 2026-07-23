<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { usePosStore } from '../stores/pos'
import AbsenDialog from '../components/AbsenDialog.vue'

const router = useRouter()
const pos = usePosStore()

const terminalCode = ref(localStorage.getItem('pos_terminal_code') || '')
const username = ref('')
const pin = ref('')
const error = ref('')
const loading = ref(false)
const showAbsen = ref(false)

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
  <div class="relative min-h-screen flex items-center justify-center p-4 overflow-hidden bg-gradient-to-br from-brand-700 via-brand-800 to-brand-900">
    <!-- ===== Doodle olahraga (latar) ===== -->
    <div class="pointer-events-none absolute inset-0 text-white/[0.07]" aria-hidden="true">
      <svg class="doodle absolute top-[8%] left-[6%] w-24 h-24 -rotate-12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <circle cx="12" cy="12" r="9" /><path d="M12 7l3 2-1 3.5h-4L9 9z" /><path d="M12 7V3.5M15 9l3-1.5M14 12.5l2.5 2.5M10 12.5L7.5 15M9 9L6 7.5" />
      </svg>
      <svg class="doodle absolute top-[12%] right-[8%] w-28 h-28 rotate-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <circle cx="12" cy="12" r="9" /><path d="M12 3v18M3 12h18M5.6 5.6C8 8 8 16 5.6 18.4M18.4 5.6C16 8 16 16 18.4 18.4" />
      </svg>
      <svg class="doodle absolute top-[46%] left-[9%] w-20 h-20 rotate-12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <circle cx="12" cy="18" r="3" /><path d="M12 15l-4-9M12 15l4-9M12 15l-1.5-9.5M12 15l1.5-9.5M8 6l8 0" />
      </svg>
      <svg class="doodle absolute bottom-[10%] right-[10%] w-24 h-24 -rotate-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <ellipse cx="9" cy="9" rx="5" ry="6" transform="rotate(-30 9 9)" /><path d="M12.5 12.5L20 20" /><path d="M6.5 6.5l5 5M9 5l3 6M5 9l6 3" />
      </svg>
      <svg class="doodle absolute bottom-[14%] left-[13%] w-16 h-16 rotate-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <path d="M3 10h11l4 2v3a4 4 0 0 1-8 0H3z" /><circle cx="9" cy="14" r="2" /><path d="M14 8V5" />
      </svg>
      <svg class="doodle absolute top-[64%] right-[20%] w-16 h-16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <circle cx="12" cy="13" r="7" /><path d="M12 13V9M10 3h4M18 6l1.5-1.5" />
      </svg>
      <svg class="doodle absolute top-[28%] right-[34%] w-20 h-20 -rotate-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <path d="M7 8h10a4 4 0 0 1 4 4l-1 4a2.5 2.5 0 0 1-4.3 1L14 15h-4l-1.7 2A2.5 2.5 0 0 1 4 16l-1-4a4 4 0 0 1 4-4z" /><path d="M7.5 11v2M6.5 12h2M15.5 11.5h.01M17 13h.01" />
      </svg>
      <svg class="doodle absolute top-[6%] left-[44%] w-16 h-16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <path d="M8 4h8v4a4 4 0 0 1-8 0zM8 5H5v2a3 3 0 0 0 3 3M16 5h3v2a3 3 0 0 1-3 3M12 12v4M9 20h6M10 16h4v4h-4z" />
      </svg>
      <svg class="doodle absolute top-[78%] left-[38%] w-20 h-20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <path d="M2 20h20M6 20V8h12v12M6 8l3-3h6l3 3M9 20v-9h6v9" />
      </svg>
      <svg class="doodle absolute bottom-[6%] left-[26%] w-28 h-16" viewBox="0 0 40 12" fill="none" stroke="currentColor" stroke-width="1.2">
        <path d="M0 6c3-4 6-4 9 0s6 4 9 0 6-4 9 0 6 4 9 0" /><path d="M0 10c3-4 6-4 9 0s6 4 9 0 6-4 9 0 6 4 9 0" />
      </svg>
    </div>

    <!-- ===== Card glassmorphism ===== -->
    <div class="relative w-full max-w-sm rounded-3xl border border-white/20 bg-white/10 backdrop-blur-2xl shadow-2xl p-6">
      <div class="text-center mb-5">
        <div class="inline-flex items-center justify-center h-14 w-14 rounded-2xl bg-white/15 border border-white/20 mb-3">
          <img src="/asp-logo.png" alt="ASP Sports" class="h-7" style="filter: brightness(0) invert(1)" />
        </div>
        <h1 class="text-lg font-semibold text-white">Point of Sale</h1>
        <p class="text-xs text-white/60 mt-0.5">Login Kasir</p>
      </div>

      <div class="space-y-3">
        <input
          v-model="terminalCode"
          placeholder="Kode Terminal (mis. T-V001-01)"
          class="w-full rounded-xl bg-white/10 border border-white/20 px-3 py-2.5 text-sm text-white placeholder-white/40 focus:border-white/50 focus:ring-4 focus:ring-white/10 outline-none transition"
        />
        <input
          v-model="username"
          placeholder="Username kasir"
          autocomplete="username"
          class="w-full rounded-xl bg-white/10 border border-white/20 px-3 py-2.5 text-sm text-white placeholder-white/40 focus:border-white/50 focus:ring-4 focus:ring-white/10 outline-none transition"
        />

        <div class="flex justify-center gap-2 py-1">
          <span
            v-for="n in 4"
            :key="n"
            class="h-3 w-3 rounded-full transition"
            :class="pin.length >= n ? 'bg-white' : 'bg-white/25'"
          />
        </div>

        <div class="grid grid-cols-3 gap-2">
          <button
            v-for="d in ['1','2','3','4','5','6','7','8','9']"
            :key="d"
            @click="tap(d)"
            class="py-3 rounded-xl bg-white/10 hover:bg-white/20 border border-white/10 text-xl font-semibold text-white active:scale-95 transition"
          >
            {{ d }}
          </button>
          <button @click="backspace" class="py-3 rounded-xl bg-white/10 hover:bg-white/20 border border-white/10 text-white/70 active:scale-95 transition">⌫</button>
          <button @click="tap('0')" class="py-3 rounded-xl bg-white/10 hover:bg-white/20 border border-white/10 text-xl font-semibold text-white active:scale-95 transition">0</button>
          <button
            @click="submit"
            :disabled="loading"
            class="py-3 rounded-xl bg-white text-brand-700 hover:bg-brand-50 font-semibold active:scale-95 disabled:opacity-60 shadow-lg transition"
          >
            {{ loading ? '…' : 'OK' }}
          </button>
        </div>

        <p v-if="error" class="text-sm text-center text-red-50 bg-red-500/25 border border-red-300/30 rounded-xl px-3 py-2">{{ error }}</p>

        <!-- Absensi: buka dialog (kamera + PIN) -->
        <div class="pt-3 mt-1 border-t border-white/15">
          <button @click="showAbsen = true"
            class="w-full py-2.5 rounded-xl bg-white/10 hover:bg-white/20 border border-white/15 text-white text-sm font-semibold active:scale-95 transition">
            🕐 Absen Masuk / Pulang
          </button>
        </div>
      </div>

      <p class="text-center text-white/50 text-xs mt-5">© {{ new Date().getFullYear() }} ASP Sports · pos.aspsports.id</p>
    </div>

    <AbsenDialog v-if="showAbsen" :terminal-code="terminalCode" @close="showAbsen = false" />
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
