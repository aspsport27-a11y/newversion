<script setup>
import { onMounted, ref, computed } from 'vue'
import { RouterLink } from 'vue-router'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(true)
const error = ref('')
const summary = ref(null)
const growthView = ref('rupiah') // 'rupiah' | 'persen'

const isManagerLike = computed(() => ['manager_unit', 'admin_unit'].includes(auth.user?.role))

function rupiah(n) {
  return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
}

function fmtDate(iso) {
  return new Date(iso).toLocaleDateString('id-ID', { day: 'numeric', month: 'short' })
}

const revenueDelta = computed(() => {
  if (!summary.value) return null
  const { revenue_today, revenue_yesterday } = summary.value
  if (!revenue_yesterday) return null
  return Math.round(((revenue_today - revenue_yesterday) / revenue_yesterday) * 100)
})

const approvalLabel = computed(() =>
  isManagerLike.value ? 'Pengajuan Anda yang Tertunda' : 'Approval Tertunda',
)

onMounted(async () => {
  try {
    const { data } = await client.get('/admin/dashboard/summary')
    summary.value = data
  } catch (e) {
    error.value = 'Gagal memuat ringkasan dashboard.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-800">Selamat datang, {{ auth.user?.username }} 👋</h1>
    <p class="text-slate-500 mt-1">Ringkasan operasional hari ini.</p>

    <div v-if="loading" class="mt-8 text-slate-400">Memuat data…</div>
    <p v-else-if="error" class="mt-8 text-red-600">{{ error }}</p>

    <div v-else class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 mt-6">
      <!-- Omzet hari ini -->
      <div class="bg-white rounded-xl shadow-sm border p-5">
        <div class="flex items-center gap-3">
          <div class="h-11 w-11 rounded-lg bg-brand-500 flex items-center justify-center text-xl">💰</div>
          <div>
            <p class="text-xl font-bold text-slate-800">{{ rupiah(summary.revenue_today) }}</p>
            <p class="text-sm text-slate-500">Omzet Hari Ini</p>
          </div>
        </div>
        <div class="flex items-center justify-between mt-3 pt-3 border-t text-xs">
          <span class="text-slate-400">{{ summary.order_count_today }} transaksi lunas</span>
          <span v-if="revenueDelta !== null" :class="revenueDelta >= 0 ? 'text-emerald-600' : 'text-red-600'" class="font-semibold">
            {{ revenueDelta >= 0 ? '▲' : '▼' }} {{ Math.abs(revenueDelta) }}% vs kemarin
          </span>
        </div>
      </div>

      <!-- Approval tertunda -->
      <div class="bg-white rounded-xl shadow-sm border p-5">
        <div class="flex items-center gap-3">
          <div class="h-11 w-11 rounded-lg bg-amber-500 flex items-center justify-center text-xl">📝</div>
          <div>
            <p class="text-xl font-bold text-slate-800">{{ summary.approvals_pending.total }}</p>
            <p class="text-sm text-slate-500">{{ approvalLabel }}</p>
          </div>
        </div>
        <div class="mt-3 pt-3 border-t space-y-1.5 text-xs">
          <RouterLink :to="{ name: 'operational' }" class="flex justify-between text-slate-500 hover:text-brand-600">
            <span>Operasional</span><span class="font-semibold">{{ summary.approvals_pending.ops }}</span>
          </RouterLink>
          <RouterLink :to="{ name: 'payroll' }" class="flex justify-between text-slate-500 hover:text-brand-600">
            <span>Payroll</span><span class="font-semibold">{{ summary.approvals_pending.payroll }}</span>
          </RouterLink>
          <RouterLink :to="{ name: 'procurement' }" class="flex justify-between text-slate-500 hover:text-brand-600">
            <span>Procurement</span><span class="font-semibold">{{ summary.approvals_pending.procurement }}</span>
          </RouterLink>
        </div>
      </div>

      <!-- Stok menipis -->
      <div class="bg-white rounded-xl shadow-sm border p-5">
        <div class="flex items-center gap-3">
          <div class="h-11 w-11 rounded-lg bg-red-500 flex items-center justify-center text-xl">📦</div>
          <div>
            <p class="text-xl font-bold text-slate-800">{{ summary.low_stock.count }}</p>
            <p class="text-sm text-slate-500">Produk Stok Menipis</p>
          </div>
        </div>
        <div v-if="summary.low_stock.items.length" class="mt-3 pt-3 border-t space-y-1 text-xs max-h-28 overflow-auto">
          <div v-for="p in summary.low_stock.items" :key="p.id" class="flex justify-between text-slate-500">
            <span class="truncate pr-2">{{ p.name }}</span>
            <span class="shrink-0 font-semibold text-red-600">{{ p.stock_qty }} / {{ p.min_stock }}</span>
          </div>
        </div>
        <RouterLink v-if="summary.low_stock.count" :to="{ name: 'products' }" class="block mt-2 text-xs text-brand-600 hover:text-brand-700">
          Lihat semua produk →
        </RouterLink>
      </div>
    </div>

    <!-- Sales Growth MoM per venue -->
    <div v-if="!loading && !error" class="bg-white rounded-xl shadow-sm border p-5 mt-4">
      <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h3 class="font-semibold text-slate-700">Sales Growth MoM per Venue</h3>
        <div class="flex items-center gap-3">
          <p class="text-xs text-slate-400">
            {{ fmtDate(summary.sales_growth_mom.this_month_range.from) }}–{{ fmtDate(summary.sales_growth_mom.this_month_range.to) }}
            vs
            {{ fmtDate(summary.sales_growth_mom.last_month_range.from) }}–{{ fmtDate(summary.sales_growth_mom.last_month_range.to) }}
          </p>
          <div class="flex rounded-lg border border-slate-200 overflow-hidden text-xs shrink-0">
            <button
              @click="growthView = 'rupiah'"
              :class="growthView === 'rupiah' ? 'bg-brand-600 text-white' : 'bg-white text-slate-500 hover:bg-slate-50'"
              class="px-3 py-1.5 font-medium transition"
            >Rupiah</button>
            <button
              @click="growthView = 'persen'"
              :class="growthView === 'persen' ? 'bg-brand-600 text-white' : 'bg-white text-slate-500 hover:bg-slate-50'"
              class="px-3 py-1.5 font-medium transition border-l border-slate-200"
            >Persentase</button>
          </div>
        </div>
      </div>
      <div v-if="!summary.sales_growth_mom.venues.length" class="text-sm text-slate-400 text-center py-4">
        Belum ada data venue untuk ditampilkan.
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-slate-400 border-b">
              <th class="pb-2 font-medium">Venue</th>
              <th v-if="growthView === 'rupiah'" class="pb-2 font-medium text-right">Bulan Ini</th>
              <th v-if="growthView === 'rupiah'" class="pb-2 font-medium text-right">Bulan Lalu</th>
              <th class="pb-2 font-medium text-right">Growth</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="v in summary.sales_growth_mom.venues" :key="v.venue_id" class="border-b last:border-0">
              <td class="py-2.5 text-slate-700">
                {{ v.venue_name }}
                <span class="text-[11px] text-slate-400 ml-1">{{ v.venue_type }}</span>
              </td>
              <td v-if="growthView === 'rupiah'" class="py-2.5 text-right text-slate-700">{{ rupiah(v.this_month) }}</td>
              <td v-if="growthView === 'rupiah'" class="py-2.5 text-right text-slate-500">{{ rupiah(v.last_month) }}</td>
              <td class="py-2.5 text-right font-semibold">
                <span v-if="v.is_new" class="text-emerald-600">Baru</span>
                <span v-else-if="v.growth_pct === null" class="text-slate-400">–</span>
                <span v-else :class="v.growth_pct >= 0 ? 'text-emerald-600' : 'text-red-600'">
                  {{ v.growth_pct >= 0 ? '▲' : '▼' }} {{ Math.abs(v.growth_pct) }}%
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
