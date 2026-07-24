<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import QRCode from 'qrcode'
import { usePosStore } from '../stores/pos'

const props = defineProps({
  paymentId: { type: Number, required: true },
  amount: { type: Number, default: 0 },
})
const emit = defineEmits(['paid', 'close'])

const pos = usePosStore()

const qrDataUrl = ref('')
const status = ref('pending')
const expiresAt = ref(null)
const now = ref(Date.now())
const error = ref('')
const checking = ref(false)

let pollTimer = null
let tickTimer = null

// Backend mengirim UTC tanpa akhiran 'Z' — tanpa ini browser salah membacanya
// sebagai waktu lokal dan hitung mundur jadi kacau (lihat utils/datetime.js).
function parseUTC(s) {
  if (!s) return null
  return new Date(/[Z+]|-\d{2}:\d{2}$/.test(s) ? s : s + 'Z')
}

const secondsLeft = computed(() => {
  if (!expiresAt.value) return null
  return Math.max(0, Math.floor((expiresAt.value.getTime() - now.value) / 1000))
})
const countdown = computed(() => {
  const s = secondsLeft.value
  if (s === null) return ''
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
})
const expired = computed(() => status.value === 'failed' || secondsLeft.value === 0)

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }

async function render(qrContent) {
  if (!qrContent || qrDataUrl.value) return
  try {
    qrDataUrl.value = await QRCode.toDataURL(qrContent, { width: 320, margin: 1 })
  } catch (e) {
    error.value = 'QR gagal ditampilkan.'
  }
}

function apply(data) {
  status.value = data.status
  expiresAt.value = parseUTC(data.qr_expires_at)
  render(data.qr_content)
  if (data.status === 'paid') {
    stop()
    emit('paid', data)
  }
}

async function poll() {
  try {
    apply(await pos.qrisStatus(props.paymentId))
  } catch (e) {
    // jaringan putus sesaat jangan bikin kasir panik — polling lanjut saja
  }
}

// Tombol manual: server benar-benar bertanya ke BRI (cadangan kalau webhook telat)
async function checkNow() {
  checking.value = true
  error.value = ''
  try {
    apply(await pos.qrisSync(props.paymentId))
    if (status.value === 'pending') error.value = 'Belum ada pembayaran masuk.'
  } catch (e) {
    error.value = e?.response?.data?.message || 'Gagal menghubungi bank.'
  } finally {
    checking.value = false
  }
}

function stop() {
  clearInterval(pollTimer); clearInterval(tickTimer)
  pollTimer = tickTimer = null
}

onMounted(async () => {
  await poll()
  pollTimer = setInterval(poll, 3000)          // status dari DB (webhook yg mengisi)
  tickTimer = setInterval(() => { now.value = Date.now() }, 1000)
})
onUnmounted(stop)
</script>

<template>
  <div class="fixed inset-0 z-50 bg-black/60 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-sm rounded-t-2xl sm:rounded-2xl p-5 max-h-[95vh] overflow-auto">
      <div class="flex justify-between items-center mb-3">
        <h3 class="text-lg font-bold text-slate-800">Bayar QRIS</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl" aria-label="Tutup">✕</button>
      </div>

      <div class="text-center mb-3">
        <p class="text-sm text-slate-500">Jumlah dibayar</p>
        <p class="text-3xl font-bold text-brand-700">{{ rupiah(amount) }}</p>
      </div>

      <!-- LUNAS -->
      <div v-if="status === 'paid'" class="text-center py-8">
        <div class="text-5xl mb-3">✅</div>
        <p class="text-lg font-bold text-emerald-700">Pembayaran diterima</p>
        <p class="text-sm text-slate-500 mt-1">Struk akan dicetak.</p>
      </div>

      <!-- KEDALUWARSA / GAGAL -->
      <div v-else-if="expired" class="text-center py-8">
        <div class="text-5xl mb-3">⌛</div>
        <p class="text-lg font-bold text-red-600">QR kedaluwarsa</p>
        <p class="text-sm text-slate-500 mt-1">Batalkan lalu buat transaksi baru.</p>
        <button @click="emit('close')" class="mt-4 w-full py-3 rounded-lg bg-slate-200 text-slate-700 font-semibold">
          Tutup
        </button>
      </div>

      <!-- MENUNGGU PEMBAYARAN -->
      <div v-else>
        <div class="bg-slate-50 border border-slate-200 rounded-xl p-3 flex items-center justify-center min-h-[280px]">
          <img v-if="qrDataUrl" :src="qrDataUrl" alt="QRIS" class="w-full max-w-[280px]" />
          <p v-else class="text-sm text-slate-400">Menyiapkan QR…</p>
        </div>

        <p class="text-center text-sm text-slate-600 mt-3">
          Minta customer memindai QR ini dengan aplikasi bank / e-wallet.
        </p>

        <div class="flex items-center justify-center gap-2 mt-3 text-sm">
          <span class="inline-block h-2 w-2 rounded-full bg-amber-500 animate-pulse"></span>
          <span class="text-slate-500">Menunggu pembayaran…</span>
          <span v-if="countdown" class="font-mono font-semibold text-slate-700">{{ countdown }}</span>
        </div>

        <p v-if="error" class="text-center text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-3">
          {{ error }}
        </p>

        <div class="grid grid-cols-2 gap-2 mt-4">
          <button @click="checkNow" :disabled="checking"
            class="py-3 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold disabled:opacity-50">
            {{ checking ? 'Mengecek…' : 'Cek status' }}
          </button>
          <button @click="emit('close')"
            class="py-3 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold">
            Tutup
          </button>
        </div>
        <p class="text-center text-[11px] text-slate-400 mt-3">
          Status terupdate otomatis begitu bank mengonfirmasi.
        </p>
      </div>
    </div>
  </div>
</template>
