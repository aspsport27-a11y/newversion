<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  total: Number,
  allowDp: { type: Boolean, default: true },
  title: { type: String, default: 'Pembayaran' },
})
const emit = defineEmits(['close', 'pay'])

const method = ref('cash')
const amount = ref(props.total) // jumlah dibayar sekarang
const received = ref('') // uang tunai diterima (untuk kembalian)
const reference = ref('')
const submitting = ref(false)

const sisa = computed(() => Math.max(0, props.total - (Number(amount.value) || 0)))
const change = computed(() => Math.max(0, (Number(received.value) || 0) - (Number(amount.value) || 0)))
const validAmount = computed(() => {
  const a = Number(amount.value) || 0
  return a > 0 && a <= props.total
})
const canPayCash = computed(() => validAmount.value && (Number(received.value) || 0) >= (Number(amount.value) || 0))

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function setDp() { amount.value = Math.round(props.total / 2) }
function setFull() { amount.value = props.total }
function quickReceived(v) { received.value = String(v) }

async function confirm() {
  submitting.value = true
  try {
    await emit('pay', {
      method: method.value,
      amount: Number(amount.value),
      reference: method.value === 'qris' ? reference.value : null,
    })
  } finally { submitting.value = false }
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">{{ title }}</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <div class="text-center mb-4">
        <p class="text-sm text-slate-500">Total tagihan</p>
        <p class="text-3xl font-bold text-brand-700">{{ rupiah(total) }}</p>
      </div>

      <!-- Jumlah dibayar (DP / penuh) -->
      <div v-if="allowDp" class="mb-4">
        <div class="flex justify-between items-center mb-1">
          <label class="text-sm text-slate-600">Jumlah dibayar sekarang</label>
          <div class="flex gap-1">
            <button @click="setDp" class="text-xs bg-amber-100 text-amber-700 rounded px-2 py-1">DP 50%</button>
            <button @click="setFull" class="text-xs bg-slate-100 text-slate-600 rounded px-2 py-1">Penuh</button>
          </div>
        </div>
        <input v-model.number="amount" type="number" inputmode="numeric"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-lg text-right outline-none focus:border-brand-500" />
        <p v-if="sisa > 0" class="text-sm text-amber-600 mt-1 text-right">Sisa (DP): {{ rupiah(sisa) }}</p>
      </div>

      <div class="grid grid-cols-2 gap-2 mb-4">
        <button @click="method = 'cash'" :class="method === 'cash' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600'" class="py-2.5 rounded-lg font-medium">💵 Cash</button>
        <button @click="method = 'qris'" :class="method === 'qris' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600'" class="py-2.5 rounded-lg font-medium">📱 QRIS</button>
      </div>

      <!-- CASH -->
      <div v-if="method === 'cash'" class="space-y-3">
        <input v-model="received" type="number" inputmode="numeric" placeholder="Uang diterima"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-lg text-right outline-none focus:border-brand-500" />
        <div class="grid grid-cols-4 gap-2">
          <button v-for="v in [amount, 50000, 100000, 200000]" :key="v" @click="quickReceived(v)"
            class="py-1.5 text-xs rounded bg-slate-100 hover:bg-slate-200 text-slate-600">
            {{ v === amount ? 'Pas' : (v / 1000) + 'rb' }}
          </button>
        </div>
        <div class="flex justify-between text-sm">
          <span class="text-slate-500">Kembalian</span>
          <span class="font-semibold text-slate-800">{{ rupiah(change) }}</span>
        </div>
        <button @click="confirm" :disabled="!canPayCash || submitting"
          class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50">
          {{ submitting ? 'Memproses…' : (sisa > 0 ? 'Bayar DP & Cetak' : 'Bayar & Cetak Struk') }}
        </button>
      </div>

      <!-- QRIS -->
      <div v-else class="space-y-3">
        <div class="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
          Integrasi BRIAPI (QRIS Dinamis) menyusul. Transaksi tercatat
          <span class="font-medium">pending</span> menunggu konfirmasi.
        </div>
        <input v-model="reference" placeholder="No. referensi (opsional)"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500" />
        <button @click="confirm" :disabled="!validAmount || submitting"
          class="w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-semibold disabled:opacity-50">
          {{ submitting ? 'Memproses…' : 'Buat Transaksi QRIS' }}
        </button>
      </div>
    </div>
  </div>
</template>
