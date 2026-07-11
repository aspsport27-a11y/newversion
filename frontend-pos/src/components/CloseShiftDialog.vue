<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ shift: Object })
const emit = defineEmits(['close', 'submit'])

const countedCash = ref('')
const deposit = ref('')
const notes = ref('')
const submitting = ref(false)

const expected = computed(() => {
  const s = props.shift
  return (
    Number(s.opening_cash || 0) +
    Number(s.total_cash_sales || 0) +
    Number(s.cash_in || 0) -
    Number(s.cash_out || 0)
  )
})
const variance = computed(() => (Number(countedCash.value) || 0) - expected.value)

function rupiah(n) {
  return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
}
async function submit() {
  submitting.value = true
  try {
    await emit('submit', {
      counted_cash: Number(countedCash.value) || 0,
      deposit_amount: deposit.value === '' ? null : Number(deposit.value),
      notes: notes.value,
    })
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
    <div class="bg-white w-full max-w-md rounded-2xl p-5 max-h-[90vh] overflow-auto">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">Tutup Shift</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <div class="space-y-1.5 text-sm bg-slate-50 rounded-lg p-3 mb-4">
        <div class="flex justify-between"><span class="text-slate-500">Saldo awal</span><span>{{ rupiah(shift.opening_cash) }}</span></div>
        <div class="flex justify-between"><span class="text-slate-500">Penjualan cash</span><span>{{ rupiah(shift.total_cash_sales) }}</span></div>
        <div class="flex justify-between"><span class="text-slate-500">Penjualan QRIS</span><span>{{ rupiah(shift.total_qris_sales) }}</span></div>
        <div class="flex justify-between"><span class="text-slate-500">Kas masuk / keluar</span><span>{{ rupiah(shift.cash_in) }} / {{ rupiah(shift.cash_out) }}</span></div>
        <div class="flex justify-between font-semibold border-t pt-1.5"><span>Kas seharusnya</span><span>{{ rupiah(expected) }}</span></div>
      </div>

      <label class="block text-sm text-slate-600 mb-1">Uang tunai dihitung</label>
      <input v-model="countedCash" type="number" inputmode="numeric" placeholder="0"
        class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-lg text-right outline-none focus:border-brand-500 mb-1" />
      <div class="flex justify-between text-sm mb-3">
        <span class="text-slate-500">Selisih</span>
        <span :class="variance === 0 ? 'text-emerald-600' : 'text-red-600'" class="font-semibold">{{ rupiah(variance) }}</span>
      </div>

      <label class="block text-sm text-slate-600 mb-1">Setoran (opsional)</label>
      <input v-model="deposit" type="number" inputmode="numeric" placeholder="0"
        class="w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-brand-500 mb-3" />

      <textarea v-model="notes" placeholder="Catatan (opsional)" rows="2"
        class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500 mb-4"></textarea>

      <button @click="submit" :disabled="submitting"
        class="w-full py-3 rounded-lg bg-red-600 hover:bg-red-700 text-white font-semibold disabled:opacity-50">
        {{ submitting ? 'Menutup…' : 'Tutup Shift' }}
      </button>
    </div>
  </div>
</template>
