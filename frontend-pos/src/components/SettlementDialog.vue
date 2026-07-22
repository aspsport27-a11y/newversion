<script setup>
import { ref, onMounted } from 'vue'
import { usePosStore } from '../stores/pos'
import PaymentDialog from './PaymentDialog.vue'

const pos = usePosStore()
const emit = defineEmits(['close', 'paid'])

const orders = ref([])
const loading = ref(true)
const selected = ref(null)
const err = ref('')

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
const ICONS = { booking: '🏟️', rental: '🎮', ticket: '🎟️', product: '🧾' }
function itemIcon(type) { return ICONS[type] || '🧾' }

async function load() {
  loading.value = true
  try {
    orders.value = await pos.fetchOutstanding()
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function onPay(payload) {
  err.value = ''
  try {
    const res = await pos.settle(selected.value.id, payload.method, payload.amount, payload.reference)
    emit('paid', res)
  } catch (e) {
    err.value = e?.response?.data?.message || 'Gagal memproses pelunasan.'
  }
}

const msg = ref('')
async function cancel(o) {
  if (!window.confirm(`Batalkan booking a/n ${o.customer_name || 'tanpa nama'}?\nDP yang sudah dibayar HANGUS (tidak dikembalikan) dan slot dilepas.`)) return
  err.value = ''
  try {
    await pos.cancelOrder(o.id)
    msg.value = `Booking ${o.order_number} dibatalkan.`
    await load()
  } catch (e) {
    err.value = e?.response?.data?.message || 'Gagal membatalkan.'
  }
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">Order Belum Bayar</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <p v-if="loading" class="text-center text-slate-400 py-6">Memuat…</p>
      <p v-else-if="!orders.length" class="text-center text-slate-400 py-6">
        Tidak ada order yang belum lunas 🎉
      </p>

      <div v-else class="space-y-2">
        <div v-for="o in orders" :key="o.id" class="border rounded-xl p-3">
          <div class="flex justify-between items-start">
            <div>
              <p class="font-medium text-slate-800">{{ o.customer_name || 'Tanpa nama' }}</p>
              <p class="text-xs text-slate-400 font-mono">{{ o.order_number }}</p>
              <p v-for="it in o.items" :key="it.id" class="text-xs text-slate-500">
                {{ itemIcon(it.item_type) }} {{ it.name }}
              </p>
            </div>
            <div class="text-right">
              <p class="text-xs text-slate-400">sisa</p>
              <p class="font-bold text-amber-600">{{ rupiah(o.amount_due) }}</p>
            </div>
          </div>
          <div class="flex gap-2 mt-2">
            <button @click="selected = o" class="flex-1 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium">Bayar Pelunasan</button>
            <button @click="cancel(o)" class="py-2 px-3 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 text-sm font-medium">Batalkan</button>
          </div>
        </div>
      </div>

      <p v-if="msg" class="text-sm text-emerald-600 bg-emerald-50 rounded-lg px-3 py-2 mt-3">{{ msg }}</p>
      <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mt-3">{{ err }}</p>
    </div>

    <!-- Bayar pelunasan -->
    <PaymentDialog v-if="selected" :total="selected.amount_due" title="Pelunasan"
      @close="selected = null" @pay="onPay" />
  </div>
</template>
