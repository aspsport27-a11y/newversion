<script setup>
import { ref, onMounted, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isManager = computed(() => auth.user?.role === 'manager_unit')

const venues = ref([])
const venueId = ref('')
const today = new Date().toISOString().slice(0, 10)
const from = ref(today)
const to = ref(today)
const statusFilter = ref('')
const categoryFilter = ref('')
const search = ref('')

const orders = ref([])
const loading = ref(false)
const detail = ref(null)

const statusMap = { paid: ['Lunas', 'bg-emerald-100 text-emerald-700'], open: ['Belum Lunas', 'bg-amber-100 text-amber-700'], void: ['Dibatalkan', 'bg-red-100 text-red-600'] }

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function fmtTime(s) { return s ? new Date(s).toLocaleString('id-ID') : '—' }

async function loadVenues() {
  const { data } = await client.get('/venues')
  venues.value = data.venues
  if (isManager.value) {
    venues.value = venues.value.filter((x) => x.id === auth.user?.venue_id)
    venueId.value = auth.user?.venue_id || ''
  }
}

async function loadOrders() {
  loading.value = true
  try {
    const params = { from: from.value, to: to.value }
    if (!isManager.value && venueId.value) params.venue_id = venueId.value
    if (statusFilter.value) params.status = statusFilter.value
    const { data } = await client.get('/admin/orders', { params })
    orders.value = data.orders
  } finally { loading.value = false }
}

onMounted(async () => { await loadVenues(); await loadOrders() })

// kategori yang tersedia diambil dari transaksi yg sudah dimuat (bukan tabel
// kategori global) — biar cuma nampilin kategori yg beneran ada di hasil query ini
const availableCategories = computed(() => {
  const set = new Set()
  for (const o of orders.value) for (const c of o.categories) set.add(c)
  return [...set].sort()
})

const filtered = computed(() => {
  let list = orders.value
  if (categoryFilter.value) list = list.filter((o) => o.categories.includes(categoryFilter.value))
  const q = search.value.trim().toLowerCase()
  if (q) {
    list = list.filter((o) =>
      o.order_number.toLowerCase().includes(q) ||
      (o.cashier || '').toLowerCase().includes(q)
    )
  }
  return list
})

// ---- Paging ----
const page = ref(1)
const pageSize = ref(20)
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filtered.value.slice(start, start + pageSize.value)
})
function applyFilter() { page.value = 1; loadOrders() }

async function openDetail(o) {
  const { data } = await client.get(`/admin/orders/${o.id}`)
  detail.value = data.order
}
function venueName(id) { const v = venues.value.find((x) => x.id === id); return v ? v.code : '—' }
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-5">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">Riwayat Transaksi</h1>
        <p class="text-slate-500 mt-1">Daftar transaksi penjualan per venue, dengan detail item per kategori produk.</p>
      </div>
    </div>

    <!-- Filter -->
    <div class="bg-white rounded-xl shadow-sm border p-4 mb-5 flex flex-wrap items-end gap-3">
      <div><label class="block text-xs text-slate-500 mb-1">Dari</label>
        <input v-model="from" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <div><label class="block text-xs text-slate-500 mb-1">Sampai</label>
        <input v-model="to" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <div v-if="!isManager"><label class="block text-xs text-slate-500 mb-1">Venue</label>
        <select v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua venue</option>
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select></div>
      <div v-else><label class="block text-xs text-slate-500 mb-1">Venue</label>
        <p class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">{{ venues[0]?.code }} — {{ venues[0]?.name }}</p></div>
      <div><label class="block text-xs text-slate-500 mb-1">Status</label>
        <select v-model="statusFilter" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua status</option>
          <option value="paid">Lunas</option>
          <option value="open">Belum Lunas</option>
          <option value="void">Dibatalkan</option>
        </select></div>
      <button @click="applyFilter" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-5 py-2 font-medium">Terapkan</button>
    </div>

    <div class="mb-3 flex flex-wrap gap-2">
      <input v-model="search" type="text" placeholder="🔍 Cari kode order / kasir…"
        class="w-full max-w-sm rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
      <select v-model="categoryFilter" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
        <option value="">Semua kategori</option>
        <option v-for="c in availableCategories" :key="c" :value="c">{{ c }}</option>
      </select>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-3 font-medium">Kode</th>
            <th v-if="!isManager" class="px-4 py-3 font-medium">Venue</th>
            <th class="px-4 py-3 font-medium">Waktu</th>
            <th class="px-4 py-3 font-medium">Kasir</th>
            <th class="px-4 py-3 font-medium">Kategori</th>
            <th class="px-4 py-3 font-medium">Metode</th>
            <th class="px-4 py-3 font-medium text-right">Total</th>
            <th class="px-4 py-3 font-medium text-center">Status</th>
            <th class="px-4 py-3"></th>
          </tr></thead>
          <tbody>
            <tr v-if="loading"><td colspan="9" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!orders.length"><td colspan="9" class="px-4 py-8 text-center text-slate-400">Tidak ada transaksi pada periode ini.</td></tr>
            <tr v-else-if="!filtered.length"><td colspan="9" class="px-4 py-8 text-center text-slate-400">Tidak ada transaksi yang cocok dengan filter.</td></tr>
            <tr v-for="o in paged" :key="o.id" @click="openDetail(o)" class="border-t hover:bg-slate-50 cursor-pointer">
              <td class="px-4 py-3 font-mono text-xs text-slate-500">{{ o.order_number }}</td>
              <td v-if="!isManager" class="px-4 py-3 text-slate-600">{{ venueName(o.venue_id) }}</td>
              <td class="px-4 py-3 text-slate-500 whitespace-nowrap">{{ fmtTime(o.created_at) }}</td>
              <td class="px-4 py-3 text-slate-600">{{ o.cashier || '—' }}</td>
              <td class="px-4 py-3">
                <span v-for="c in o.categories" :key="c" class="text-[10px] bg-slate-100 text-slate-600 rounded px-1.5 py-0.5 mr-1">{{ c }}</span>
                <span v-if="!o.categories.length" class="text-slate-300 text-xs">—</span>
              </td>
              <td class="px-4 py-3 text-slate-500 capitalize">{{ o.payment_methods.join(', ') || '—' }}</td>
              <td class="px-4 py-3 text-right font-medium">{{ rupiah(o.total_amount) }}</td>
              <td class="px-4 py-3 text-center"><span :class="statusMap[o.status]?.[1]" class="text-xs rounded-full px-2 py-0.5">{{ statusMap[o.status]?.[0] || o.status }}</span></td>
              <td class="px-4 py-3 text-right text-brand-600 text-sm">Detail</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="filtered.length" class="flex items-center justify-between gap-3 px-4 py-3 border-t flex-wrap">
        <p class="text-xs text-slate-500">
          Menampilkan {{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, filtered.length) }} dari {{ filtered.length }} transaksi
        </p>
        <div class="flex items-center gap-2">
          <select v-model.number="pageSize" @change="page = 1" class="rounded-lg border border-slate-300 px-2 py-1.5 text-xs outline-none focus:border-brand-500">
            <option :value="20">20 / halaman</option>
            <option :value="50">50 / halaman</option>
            <option :value="100">100 / halaman</option>
          </select>
          <button @click="page = 1" :disabled="page === 1" class="text-xs px-2 py-1.5 rounded-lg border border-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50">«</button>
          <button @click="page--" :disabled="page === 1" class="text-xs px-2 py-1.5 rounded-lg border border-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50">‹ Sebelumnya</button>
          <span class="text-xs text-slate-500">Halaman {{ page }} / {{ totalPages }}</span>
          <button @click="page++" :disabled="page === totalPages" class="text-xs px-2 py-1.5 rounded-lg border border-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50">Berikutnya ›</button>
          <button @click="page = totalPages" :disabled="page === totalPages" class="text-xs px-2 py-1.5 rounded-lg border border-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50">»</button>
        </div>
      </div>
    </div>

    <!-- Detail modal -->
    <div v-if="detail" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="detail = null">
      <div class="bg-white w-full max-w-lg rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-start mb-3">
          <div><h3 class="text-lg font-bold text-slate-800">{{ detail.order_number }}</h3><p class="text-sm text-slate-500">{{ fmtTime(detail.created_at) }}</p></div>
          <div class="flex items-center gap-2">
            <span :class="statusMap[detail.status]?.[1]" class="text-xs rounded-full px-2 py-1">{{ statusMap[detail.status]?.[0] || detail.status }}</span>
            <button @click="detail = null" class="text-slate-400 hover:text-slate-600 text-xl leading-none">✕</button>
          </div>
        </div>
        <p class="text-sm text-slate-600 mb-1" v-if="detail.customer_name">Pelanggan: {{ detail.customer_name }} {{ detail.customer_phone ? `(${detail.customer_phone})` : '' }}</p>
        <p class="text-sm text-slate-600 mb-3" v-if="detail.cashier">Kasir: {{ detail.cashier }}</p>

        <div class="border rounded-lg overflow-hidden mb-3">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left text-xs"><tr>
              <th class="px-3 py-2">Item</th><th class="px-3 py-2">Kategori</th>
              <th class="px-3 py-2 text-right">Qty</th><th class="px-3 py-2 text-right">Subtotal</th>
            </tr></thead>
            <tbody>
              <tr v-for="it in detail.items" :key="it.id" class="border-t">
                <td class="px-3 py-2 text-slate-700">{{ it.name }}</td>
                <td class="px-3 py-2 text-slate-500 text-xs">{{ it.category_name || '—' }}</td>
                <td class="px-3 py-2 text-right">{{ it.quantity }}</td>
                <td class="px-3 py-2 text-right">{{ rupiah(it.line_total) }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="border-t bg-slate-50"><td class="px-3 py-2" colspan="3">Subtotal</td><td class="px-3 py-2 text-right">{{ rupiah(detail.subtotal) }}</td></tr>
              <tr v-if="detail.discount_amount"><td class="px-3 py-2" colspan="3">Diskon</td><td class="px-3 py-2 text-right text-amber-600">-{{ rupiah(detail.discount_amount) }}</td></tr>
              <tr class="border-t bg-slate-50 font-semibold"><td class="px-3 py-2" colspan="3">Total</td><td class="px-3 py-2 text-right">{{ rupiah(detail.total_amount) }}</td></tr>
            </tfoot>
          </table>
        </div>

        <div class="mb-1">
          <p class="text-xs font-medium text-slate-500 mb-1">Pembayaran</p>
          <div v-if="!detail.payments.length" class="text-sm text-slate-400">Belum ada pembayaran.</div>
          <div v-for="p in detail.payments" :key="p.id" class="flex justify-between text-sm py-1 border-t">
            <span class="capitalize text-slate-600">{{ p.method }} <span class="text-xs text-slate-400">{{ fmtTime(p.paid_at) }}</span></span>
            <span class="font-medium">{{ rupiah(p.amount) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
