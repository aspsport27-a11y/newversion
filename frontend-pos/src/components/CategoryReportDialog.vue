<script setup>
import { ref, onMounted } from 'vue'
import client from '../api/client'

const emit = defineEmits(['close'])

const loading = ref(true)
const err = ref('')
const report = ref(null)

function rupiah(n) {
  return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
}

async function load() {
  loading.value = true
  err.value = ''
  try {
    const { data } = await client.get('/reports/category-daily')
    report.value = data
  } catch (e) {
    err.value = e?.response?.data?.message || 'Gagal memuat laporan.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" @click.self="emit('close')">
    <div class="bg-white w-full max-w-sm rounded-2xl p-5 max-h-[85vh] overflow-auto">
      <div class="flex justify-between items-center mb-3">
        <h3 class="text-lg font-bold text-slate-800">📊 Laporan Hari Ini</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <div v-if="loading" class="text-center text-slate-400 text-sm py-6">Memuat…</div>
      <p v-else-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{{ err }}</p>
      <template v-else>
        <p class="text-xs text-slate-400 mb-3">{{ report.date }} · {{ report.order_count }} transaksi lunas</p>

        <div v-if="!report.by_category.length" class="text-center text-slate-400 text-sm py-6">
          Belum ada penjualan hari ini.
        </div>
        <div v-else class="space-y-1.5">
          <div v-for="c in report.by_category" :key="c.category"
            class="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-2.5">
            <div>
              <p class="text-sm font-medium text-slate-700">{{ c.category }}</p>
              <p class="text-[11px] text-slate-400">{{ c.qty }} item</p>
            </div>
            <span class="font-bold text-brand-700 text-sm">{{ rupiah(c.amount) }}</span>
          </div>
        </div>

        <div class="flex justify-between items-center border-t mt-3 pt-3">
          <span class="font-semibold text-slate-700">Total</span>
          <span class="font-bold text-lg text-emerald-700">{{ rupiah(report.total) }}</span>
        </div>
      </template>
    </div>
  </div>
</template>
