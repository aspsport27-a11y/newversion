<script setup>
import { ref, onMounted, computed } from 'vue'
import { usePosStore } from '../stores/pos'
import { parseUTC } from '../utils/datetime'

const pos = usePosStore()
const emit = defineEmits(['close', 'changed'])

const orders = ref([])
const loading = ref(true)
const busy = ref(false)
const err = ref('')
const search = ref('')

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function fmtTime(s) { return s ? parseUTC(s).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) : '' }
const statusMap = { paid: ['Lunas', 'bg-emerald-100 text-emerald-700'], open: ['Belum bayar', 'bg-amber-100 text-amber-700'], partial: ['DP', 'bg-amber-100 text-amber-700'], void: ['Dibatalkan', 'bg-red-100 text-red-500'] }

async function load() {
  loading.value = true
  try { orders.value = await pos.fetchRecentOrders() }
  catch (e) { err.value = e?.response?.data?.message || 'Gagal memuat.' }
  finally { loading.value = false }
}
onMounted(load)

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return orders.value
  return orders.value.filter((o) => (o.order_number || '').toLowerCase().includes(q) || (o.customer_name || '').toLowerCase().includes(q))
})

async function cancel(o) {
  if (o.status === 'void') return
  if (!window.confirm(`Batalkan transaksi ${o.order_number}${o.customer_name ? ' — ' + o.customer_name : ''} (${rupiah(o.total_amount)})?\n\nStok dikembalikan & uang dikeluarkan dari shift ini. Lanjutkan?`)) return
  busy.value = true; err.value = ''
  try {
    await pos.cancelOrder(o.id)
    await load()
    emit('changed')
  } catch (e) { err.value = e?.response?.data?.message || 'Gagal membatalkan.' }
  finally { busy.value = false }
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-center mb-1">
        <h3 class="text-lg font-bold text-slate-800">🧾 Transaksi Shift Ini</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>
      <p class="text-xs text-slate-400 mb-3">Batalkan transaksi yang salah entry (hanya shift yang sedang berjalan). Setelah batal, input ulang dengan benar.</p>

      <input v-if="orders.length" v-model="search" type="text" placeholder="🔍 Cari kode / nama…"
        class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500 mb-3" />

      <p v-if="loading" class="text-center text-slate-400 py-6">Memuat…</p>
      <p v-else-if="!orders.length" class="text-center text-slate-400 py-6">Belum ada transaksi di shift ini.</p>
      <p v-else-if="!filtered.length" class="text-center text-slate-400 py-6">Tidak ada yang cocok.</p>

      <div v-else class="space-y-2">
        <div v-for="o in filtered" :key="o.id" class="border rounded-xl p-3" :class="o.status === 'void' ? 'opacity-60' : ''">
          <div class="flex justify-between items-start">
            <div class="min-w-0">
              <p class="font-medium text-slate-800 truncate">{{ o.customer_name || 'Umum' }}
                <span class="text-xs rounded-full px-2 py-0.5 ml-1" :class="statusMap[o.status]?.[1]">{{ statusMap[o.status]?.[0] || o.status }}</span>
              </p>
              <p class="text-xs text-slate-400 font-mono">{{ o.order_number }} · {{ fmtTime(o.created_at) }}</p>
              <p v-for="it in (o.items || []).slice(0, 4)" :key="it.id" class="text-xs text-slate-500 truncate">• {{ it.name }} <span class="text-slate-400">×{{ it.quantity }}</span></p>
              <p v-if="(o.items || []).length > 4" class="text-xs text-slate-400">+{{ o.items.length - 4 }} item lain…</p>
            </div>
            <div class="text-right pl-2">
              <p class="font-bold text-slate-800 whitespace-nowrap">{{ rupiah(o.total_amount) }}</p>
            </div>
          </div>
          <button v-if="o.status !== 'void'" @click="cancel(o)" :disabled="busy"
            class="w-full mt-2 py-2 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 text-sm font-medium disabled:opacity-50">Batalkan Transaksi</button>
        </div>
      </div>

      <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mt-3">{{ err }}</p>
    </div>
  </div>
</template>
