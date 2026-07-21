<script setup>
import { ref, onMounted, nextTick, computed } from 'vue'
import client from '../api/client'
import Chart from 'chart.js/auto'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isManager = computed(() => auth.user?.role === 'manager_unit')

const venues = ref([])
const venueId = ref('')
const today = new Date().toISOString().slice(0, 10)
const firstOfMonth = today.slice(0, 8) + '01'
const from = ref(firstOfMonth)
const to = ref(today)

const rep = ref(null)
const loading = ref(false)
let chart = null

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }

const isProfit = computed(() => (rep.value?.net_profit ?? 0) >= 0)

async function loadVenues() {
  const { data } = await client.get('/venues')
  venues.value = data.venues
  // manager_unit dibatasi ke venue-nya sendiri (backend juga sudah memaksa ini,
  // tapi picker "Semua venue" menyesatkan kalau tetap ditampilkan)
  if (isManager.value) {
    venues.value = venues.value.filter((x) => x.id === auth.user?.venue_id)
    venueId.value = auth.user?.venue_id || ''
  }
}
async function run() {
  loading.value = true
  const params = { from: from.value, to: to.value }
  if (venueId.value) params.venue_id = venueId.value
  try {
    const { data } = await client.get('/financial/report', { params })
    rep.value = data
  } finally { loading.value = false }
  await nextTick()
  renderChart()
}
function renderChart() {
  const el = document.getElementById('pnlChart')
  if (!el || !rep.value) return
  if (chart) chart.destroy()
  const net = rep.value.net_profit
  chart = new Chart(el, {
    type: 'bar',
    data: {
      labels: ['Pendapatan', 'Beban', 'Laba/Rugi'],
      datasets: [{
        data: [rep.value.revenue.total, rep.value.expenses.total, net],
        backgroundColor: ['#16a34a', '#dc2626', net >= 0 ? '#1877cc' : '#f59e0b'],
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => rupiah(c.raw) } } },
      scales: { y: { ticks: { callback: (v) => 'Rp' + (v / 1000000) + 'jt' } } },
    },
  })
}
onMounted(async () => { await loadVenues(); await run() })
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-800 mb-1">Laporan Bisnis</h1>
    <p class="text-slate-500 mb-5">Laba-rugi &amp; arus kas operasional per venue — basis kas. Tidak termasuk beban holding/owner.</p>

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
      <button @click="run" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-5 py-2 font-medium">Terapkan</button>
    </div>

    <div v-if="loading" class="text-slate-400">Memuat…</div>

    <template v-else-if="rep">
      <!-- Ringkasan -->
      <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
        <div class="bg-white rounded-xl shadow-sm border p-5">
          <p class="text-sm text-slate-500">Pendapatan</p>
          <p class="text-2xl font-bold text-emerald-600 mt-1">{{ rupiah(rep.revenue.total) }}</p>
        </div>
        <div class="bg-white rounded-xl shadow-sm border p-5">
          <p class="text-sm text-slate-500">Total Beban</p>
          <p class="text-2xl font-bold text-red-600 mt-1">{{ rupiah(rep.expenses.total) }}</p>
        </div>
        <div class="bg-white rounded-xl shadow-sm border p-5">
          <p class="text-sm text-slate-500">{{ isProfit ? 'Laba Bersih' : 'Rugi Bersih' }}</p>
          <p class="text-2xl font-bold mt-1" :class="isProfit ? 'text-brand-600' : 'text-amber-600'">{{ rupiah(rep.net_profit) }}</p>
          <p class="text-xs text-slate-400 mt-0.5">Margin {{ rep.margin_pct }}%</p>
        </div>
        <div class="bg-white rounded-xl shadow-sm border p-5">
          <p class="text-sm text-slate-500">Saldo Kas (saat ini)</p>
          <p class="text-2xl font-bold text-slate-800 mt-1">{{ rupiah(rep.cash.total) }}</p>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
        <!-- Chart -->
        <div class="bg-white rounded-xl shadow-sm border p-6">
          <h3 class="font-semibold text-slate-700 mb-4">Pendapatan vs Beban</h3>
          <div class="h-56"><canvas id="pnlChart"></canvas></div>
        </div>

        <!-- Laba-Rugi rincian -->
        <div class="bg-white rounded-xl shadow-sm border p-6">
          <h3 class="font-semibold text-slate-700 mb-4">Laba-Rugi</h3>
          <div class="text-sm">
            <div class="flex justify-between py-1.5 border-b">
              <span class="text-slate-600 font-medium">Pendapatan</span>
              <span class="font-semibold text-emerald-600">{{ rupiah(rep.revenue.total) }}</span>
            </div>
            <div v-for="m in rep.revenue.by_method" :key="m.method" class="flex justify-between py-1 pl-4 text-slate-500">
              <span class="capitalize">— {{ m.method }}</span><span>{{ rupiah(m.amount) }}</span>
            </div>
            <div v-if="rep.revenue.by_category.length" class="pl-4 mt-1 pt-1 border-t border-dashed">
              <p class="text-xs text-slate-400 mb-1">Per kategori produk</p>
              <div v-for="c in rep.revenue.by_category" :key="c.category" class="flex justify-between py-0.5 pl-2 text-slate-500 text-xs">
                <span>— {{ c.category }}</span><span>{{ rupiah(c.amount) }}</span>
              </div>
            </div>
            <div class="flex justify-between py-1.5 border-b mt-2">
              <span class="text-slate-600 font-medium">Beban</span>
              <span class="font-semibold text-red-600">({{ rupiah(rep.expenses.total) }})</span>
            </div>
            <div v-for="b in rep.expenses.breakdown" :key="b.group" class="flex justify-between py-1 pl-4 text-slate-500">
              <span>— {{ b.group }}</span><span>{{ rupiah(b.amount) }}</span>
            </div>
            <div class="flex justify-between py-2 mt-2 border-t-2 border-slate-200">
              <span class="font-bold text-slate-800">{{ isProfit ? 'Laba Bersih' : 'Rugi Bersih' }}</span>
              <span class="font-bold" :class="isProfit ? 'text-brand-600' : 'text-amber-600'">{{ rupiah(rep.net_profit) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <!-- Beban operasional per kategori -->
        <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
          <h3 class="font-semibold text-slate-700 px-4 py-3 border-b">Beban Operasional per Kategori</h3>
          <table class="w-full text-sm">
            <tbody>
              <tr v-if="!rep.expenses.operational_by_category.length">
                <td class="px-4 py-6 text-center text-slate-400">Tidak ada pengeluaran operasional pada periode ini.</td>
              </tr>
              <tr v-for="c in rep.expenses.operational_by_category" :key="c.category" class="border-t">
                <td class="px-4 py-2 text-slate-600">{{ c.category }}</td>
                <td class="px-4 py-2 text-right font-medium text-slate-700">{{ rupiah(c.amount) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Arus Kas Operasional (masuk/keluar rekening venue akibat pengajuan dana) -->
        <div v-if="isManager" class="bg-white rounded-xl shadow-sm border overflow-hidden">
          <h3 class="font-semibold text-slate-700 px-4 py-3 border-b">Arus Kas Operasional (Rekening Venue)</h3>
          <div class="grid grid-cols-2 gap-3 p-4">
            <div class="bg-emerald-50 rounded-lg px-3 py-2"><p class="text-xs text-emerald-700">Masuk</p><p class="font-bold text-emerald-700">{{ rupiah(rep.cash.operational_flow.in) }}</p></div>
            <div class="bg-red-50 rounded-lg px-3 py-2"><p class="text-xs text-red-600">Keluar</p><p class="font-bold text-red-600">{{ rupiah(rep.cash.operational_flow.out) }}</p></div>
          </div>
          <p class="text-xs text-slate-400 px-4 pb-3">Mutasi rekening venue ini yang berasal dari pengajuan dana operasional (disetujui &amp; dicairkan) pada periode di atas.</p>
        </div>

        <!-- Saldo Kas per rekening -->
        <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
          <h3 class="font-semibold text-slate-700 px-4 py-3 border-b">Saldo Kas per Rekening</h3>
          <table class="w-full text-sm">
            <tbody>
              <tr v-if="!rep.cash.accounts.length">
                <td class="px-4 py-6 text-center text-slate-400">Belum ada rekening.</td>
              </tr>
              <tr v-for="a in rep.cash.accounts" :key="a.id" class="border-t">
                <td class="px-4 py-2">
                  <span class="text-slate-700">{{ a.name }}</span>
                  <span class="ml-2 text-xs px-1.5 py-0.5 rounded" :class="a.type === 'holding' ? 'bg-indigo-50 text-indigo-600' : 'bg-slate-100 text-slate-500'">{{ a.type === 'holding' ? 'Holding' : 'Venue' }}</span>
                </td>
                <td class="px-4 py-2 text-right font-medium text-slate-700">{{ rupiah(a.balance) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
