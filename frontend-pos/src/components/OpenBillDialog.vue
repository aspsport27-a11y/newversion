<script setup>
import { ref, onMounted } from 'vue'
import { usePosStore } from '../stores/pos'
import PaymentDialog from './PaymentDialog.vue'

const pos = usePosStore()
const emit = defineEmits(['close', 'add-item', 'paid', 'print'])

const bills = ref([])
const loading = ref(true)
const payFor = ref(null)   // bill yang sedang dibayar
const err = ref('')

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
const ICONS = { booking: '🏟️', rental: '🎮', ticket: '🎟️', product: '🧾' }
function itemIcon(t) { return ICONS[t] || '🧾' }

async function load() {
  loading.value = true
  try {
    // hanya bill yang masih 'open' (tab berjalan) — bukan yg sudah DP (partial)
    const all = await pos.fetchOutstanding()
    bills.value = all.filter((o) => o.status === 'open')
  } finally { loading.value = false }
}
onMounted(load)

async function onPay(payload) {
  err.value = ''
  try {
    const res = await pos.settle(payFor.value.id, payload.method, payload.amount, payload.reference, payload.proof_image)
    payFor.value = null
    emit('paid', res)
  } catch (e) {
    err.value = e?.response?.data?.message || 'Gagal memproses pembayaran.'
  }
}

async function cancelBill(o) {
  if (!window.confirm(`Batalkan bill a/n ${o.customer_name || 'tanpa nama'} (${rupiah(o.total_amount)})?\nBill akan dihapus dari daftar. Tidak bisa dibatalkan.`)) return
  err.value = ''
  try {
    await pos.cancelOrder(o.id)
    await load()
  } catch (e) {
    err.value = e?.response?.data?.message || 'Gagal membatalkan bill.'
  }
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">Bill Terbuka</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <p v-if="loading" class="text-center text-slate-400 py-6">Memuat…</p>
      <p v-else-if="!bills.length" class="text-center text-slate-400 py-6">Tidak ada bill terbuka.</p>

      <div v-else class="space-y-2">
        <div v-for="o in bills" :key="o.id" class="border rounded-xl p-3">
          <div class="flex justify-between items-start">
            <div>
              <p class="font-medium text-slate-800">{{ o.customer_name || 'Tanpa nama' }}</p>
              <p class="text-xs text-slate-400 font-mono">{{ o.order_number }}</p>
              <p v-for="it in o.items" :key="it.id" class="text-xs text-slate-500">
                {{ itemIcon(it.item_type) }} {{ it.name }} <span class="text-slate-400">×{{ it.quantity }}</span>
              </p>
            </div>
            <div class="text-right">
              <p class="text-xs text-slate-400">total</p>
              <p class="font-bold text-brand-700">{{ rupiah(o.total_amount) }}</p>
            </div>
          </div>
          <div class="grid grid-cols-3 gap-2 mt-3">
            <button @click="emit('add-item', o)" class="py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium">➕ Item</button>
            <button @click="emit('print', o)" class="py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium">🧾 Cetak</button>
            <button @click="payFor = o" class="py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium">💳 Bayar</button>
          </div>
          <button @click="cancelBill(o)" class="w-full mt-2 py-1.5 rounded-lg text-xs text-red-500 hover:bg-red-50 font-medium">Batalkan Bill</button>
        </div>
      </div>

      <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mt-3">{{ err }}</p>
    </div>

    <!-- Tutup bill: bayar -->
    <PaymentDialog v-if="payFor" :total="payFor.amount_due" title="Bayar & Tutup Bill"
      :qris-dynamic="pos.qrisDynamic"
      @close="payFor = null" @pay="onPay" />
  </div>
</template>
