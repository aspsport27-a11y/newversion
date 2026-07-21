<script setup>
import { onMounted, ref, computed } from 'vue'
import { RouterLink } from 'vue-router'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(true)
const error = ref('')
const summary = ref(null)

const isManagerLike = computed(() => ['manager_unit', 'admin_unit'].includes(auth.user?.role))

function rupiah(n) {
  return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
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
  </div>
</template>
