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
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">Pelunasan Booking</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <p v-if="loading" class="text-center text-slate-400 py-6">Memuat…</p>
      <p v-else-if="!orders.length" class="text-center text-slate-400 py-6">
        Tidak ada booking yang belum lunas 🎉
      </p>

      <div v-else class="space-y-2">
        <button v-for="o in orders" :key="o.id" @click="selected = o"
          class="w-full text-left border rounded-xl p-3 hover:border-brand-400 transition">
          <div class="flex justify-between items-start">
            <div>
              <p class="font-medium text-slate-800">{{ o.customer_name || 'Tanpa nama' }}</p>
              <p class="text-xs text-slate-400 font-mono">{{ o.order_number }}</p>
              <p v-for="it in o.items.filter((x) => x.item_type === 'booking')" :key="it.id" class="text-xs text-slate-500">
                🏟️ {{ it.name }}
              </p>
            </div>
            <div class="text-right">
              <p class="text-xs text-slate-400">sisa</p>
              <p class="font-bold text-amber-600">{{ rupiah(o.amount_due) }}</p>
            </div>
          </div>
        </button>
      </div>

      <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mt-3">{{ err }}</p>
    </div>

    <!-- Bayar pelunasan -->
    <PaymentDialog v-if="selected" :total="selected.amount_due" title="Pelunasan"
      @close="selected = null" @pay="onPay" />
  </div>
</template>
