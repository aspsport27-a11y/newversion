<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ total: Number })
const emit = defineEmits(['close', 'pay'])

const method = ref('cash')
const received = ref('')
const reference = ref('')
const submitting = ref(false)

const change = computed(() => {
  const r = Number(received.value) || 0
  return Math.max(0, r - props.total)
})
const canPayCash = computed(() => (Number(received.value) || 0) >= props.total)

function quick(v) {
  received.value = String(v)
}
function rupiah(n) {
  return 'Rp ' + (n || 0).toLocaleString('id-ID')
}
async function confirm() {
  submitting.value = true
  try {
    await emit('pay', {
      method: method.value,
      reference: method.value === 'qris' ? reference.value : null,
    })
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 max-h-[90vh] overflow-auto">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">Pembayaran</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <div class="text-center mb-4">
        <p class="text-sm text-slate-500">Total tagihan</p>
        <p class="text-3xl font-bold text-brand-700">{{ rupiah(total) }}</p>
      </div>

      <div class="grid grid-cols-2 gap-2 mb-4">
        <button
          @click="method = 'cash'"
          :class="method === 'cash' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600'"
          class="py-2.5 rounded-lg font-medium"
        >💵 Cash</button>
        <button
          @click="method = 'qris'"
          :class="method === 'qris' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600'"
          class="py-2.5 rounded-lg font-medium"
        >📱 QRIS</button>
      </div>

      <!-- CASH -->
      <div v-if="method === 'cash'" class="space-y-3">
        <input
          v-model="received"
          type="number"
          inputmode="numeric"
          placeholder="Uang diterima"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-lg text-right outline-none focus:border-brand-500"
        />
        <div class="grid grid-cols-4 gap-2">
          <button v-for="v in [total, 50000, 100000, 200000]" :key="v" @click="quick(v)"
            class="py-1.5 text-xs rounded bg-slate-100 hover:bg-slate-200 text-slate-600">
            {{ v === total ? 'Pas' : (v/1000)+'rb' }}
          </button>
        </div>
        <div class="flex justify-between text-sm">
          <span class="text-slate-500">Kembalian</span>
          <span class="font-semibold text-slate-800">{{ rupiah(change) }}</span>
        </div>
        <button
          @click="confirm"
          :disabled="!canPayCash || submitting"
          class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50"
        >{{ submitting ? 'Memproses…' : 'Bayar & Cetak Struk' }}</button>
      </div>

      <!-- QRIS -->
      <div v-else class="space-y-3">
        <div class="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
          Integrasi BRIAPI (QRIS Dinamis) menyusul. Untuk sekarang transaksi tercatat
          <span class="font-medium">pending</span> menunggu konfirmasi.
        </div>
        <input
          v-model="reference"
          placeholder="No. referensi (opsional)"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500"
        />
        <button
          @click="confirm"
          :disabled="submitting"
          class="w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-semibold disabled:opacity-50"
        >{{ submitting ? 'Memproses…' : 'Buat Transaksi QRIS' }}</button>
      </div>
    </div>
  </div>
</template>
