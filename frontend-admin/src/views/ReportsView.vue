<script setup>
import { ref, onMounted, nextTick } from 'vue'
import client from '../api/client'
import Chart from 'chart.js/auto'

const venues = ref([])
const venueId = ref('')
const today = new Date().toISOString().slice(0, 10)
const from = ref(today)
const to = ref(today)

const sales = ref(null)
const shifts = ref([])
const loading = ref(false)
let chart = null

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }

async function loadVenues() {
  const { data } = await client.get('/admin/venues')
  venues.value = data.venues
}
async function run() {
  loading.value = true
  const params = { from: from.value, to: to.value }
  if (venueId.value) params.venue_id = venueId.value
  try {
    const [s, sh] = await Promise.all([
      client.get('/admin/reports/sales', { params }),
      client.get('/admin/reports/shifts', { params }),
    ])
    sales.value = s.data
    shifts.value = sh.data.shifts
  } finally { loading.value = false }
  // render SETELAH loading=false agar <canvas> sudah ada di DOM
  await nextTick()
  renderChart()
}
function renderChart() {
  const el = document.getElementById('salesChart')
  if (!el || !sales.value) return
  if (chart) chart.destroy()
  const d = sales.value.daily
  chart = new Chart(el, {
    type: 'bar',
    data: {
      labels: d.map((x) => x.date.slice(5)),
      datasets: [{ label: 'Revenue', data: d.map((x) => x.revenue), backgroundColor: '#1877cc', borderRadius: 4 }],
    },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { y: { ticks: { callback: (v) => 'Rp' + (v / 1000) + 'k' } } } },
  })
}
onMounted(async () => { await loadVenues(); await run() })
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-800 mb-1">Laporan</h1>
    <p class="text-slate-500 mb-5">Penjualan dan rekonsiliasi shift.</p>

    <!-- Filter -->
    <div class="bg-white rounded-xl shadow-sm border p-4 mb-5 flex flex-wrap items-end gap-3">
      <div><label class="block text-xs text-slate-500 mb-1">Dari</label>
        <input v-model="from" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <div><label class="block text-xs text-slate-500 mb-1">Sampai</label>
        <input v-model="to" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <div><label class="block text-xs text-slate-500 mb-1">Venue</label>
        <select v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua venue</option>
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select></div>
      <button @click="run" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-5 py-2 font-medium">Terapkan</button>
    </div>

    <div v-if="loading" class="text-slate-400">Memuat…</div>

    <template v-else-if="sales">
      <!-- Summary -->
      <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
        <div class="bg-white rounded-xl shadow-sm border p-5">
          <p class="text-sm text-slate-500">Total Penjualan</p>
          <p class="text-2xl font-bold text-slate-800 mt-1">{{ rupiah(sales.total_revenue) }}</p>
        </div>
        <div class="bg-white rounded-xl shadow-sm border p-5">
          <p class="text-sm text-slate-500">Jumlah Order</p>
          <p class="text-2xl font-bold text-slate-800 mt-1">{{ sales.order_count }}</p>
        </div>
        <div class="bg-white rounded-xl shadow-sm border p-5">
          <p class="text-sm text-slate-500 mb-1">Per Metode</p>
          <p v-for="m in sales.by_method" :key="m.method" class="text-sm flex justify-between">
            <span class="capitalize text-slate-600">{{ m.method }}</span><span class="font-medium">{{ rupiah(m.amount) }}</span>
          </p>
          <p v-if="!sales.by_method.length" class="text-sm text-slate-400">—</p>
        </div>
        <div class="bg-white rounded-xl shadow-sm border p-5">
          <p class="text-sm text-slate-500 mb-1">Per Jenis</p>
          <p v-for="t in sales.by_item_type" :key="t.item_type" class="text-sm flex justify-between">
            <span class="capitalize text-slate-600">{{ t.item_type }}</span><span class="font-medium">{{ rupiah(t.amount) }}</span>
          </p>
          <p v-if="!sales.by_item_type.length" class="text-sm text-slate-400">—</p>
        </div>
      </div>

      <!-- Chart -->
      <div class="bg-white rounded-xl shadow-sm border p-6 mb-5">
        <h3 class="font-semibold text-slate-700 mb-4">Tren Harian</h3>
        <div class="h-56"><canvas id="salesChart"></canvas></div>
      </div>

      <!-- Shifts -->
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <h3 class="font-semibold text-slate-700 px-4 py-3 border-b">Rekonsiliasi Shift</h3>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-4 py-2 font-medium">Kasir</th>
              <th class="px-4 py-2 font-medium">Buka</th>
              <th class="px-4 py-2 font-medium text-right">Cash</th>
              <th class="px-4 py-2 font-medium text-right">QRIS</th>
              <th class="px-4 py-2 font-medium text-right">Seharusnya</th>
              <th class="px-4 py-2 font-medium text-right">Dihitung</th>
              <th class="px-4 py-2 font-medium text-right">Selisih</th>
            </tr></thead>
            <tbody>
              <tr v-if="!shifts.length"><td colspan="7" class="px-4 py-6 text-center text-slate-400">Tidak ada shift.</td></tr>
              <tr v-for="s in shifts" :key="s.id" class="border-t">
                <td class="px-4 py-2 text-slate-700">{{ s.cashier || '—' }}</td>
                <td class="px-4 py-2 text-slate-500">{{ s.opened_at ? new Date(s.opened_at).toLocaleString('id-ID') : '—' }}</td>
                <td class="px-4 py-2 text-right">{{ rupiah(s.total_cash_sales) }}</td>
                <td class="px-4 py-2 text-right">{{ rupiah(s.total_qris_sales) }}</td>
                <td class="px-4 py-2 text-right">{{ rupiah(s.expected_cash) }}</td>
                <td class="px-4 py-2 text-right">{{ s.counted_cash != null ? rupiah(s.counted_cash) : '—' }}</td>
                <td class="px-4 py-2 text-right font-medium" :class="s.cash_variance === 0 ? 'text-emerald-600' : (s.cash_variance == null ? 'text-slate-400' : 'text-red-600')">
                  {{ s.cash_variance != null ? rupiah(s.cash_variance) : '—' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
