<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '../api/client'

const emit = defineEmits(['close'])

const loading = ref(true)
const err = ref('')
const report = ref(null)
const open = ref(new Set()) // kategori yg sedang di-expand
const selDate = ref(new Date().toISOString().slice(0, 10))
const tab = ref('all') // all | cash | qris | transfer

function rupiah(n) {
  return 'Rp ' + Math.round(Number(n) || 0).toLocaleString('id-ID')
}
// tab metode: label + total (dari by_method)
const methodTabs = [
  { key: 'cash', label: 'Cash' },
  { key: 'qris', label: 'QRIS' },
  { key: 'transfer', label: 'Transfer' },
]
function methodTotal(key) {
  return report.value?.by_method?.find((m) => m.method === key)?.amount || 0
}
// kategori yg ditampilkan sesuai tab aktif
const shownCategories = computed(() => {
  if (!report.value) return []
  if (tab.value === 'all') return report.value.by_category
  return report.value.by_method_category?.[tab.value] || []
})
function toggle(cat) {
  const s = new Set(open.value)
  s.has(cat) ? s.delete(cat) : s.add(cat)
  open.value = s
}
function print() {
  window.print()
}

async function load() {
  loading.value = true
  err.value = ''
  try {
    const { data } = await client.get('/reports/category-daily', { params: { date: selDate.value } })
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
      <div class="flex justify-between items-center mb-2 no-print">
        <h3 class="text-lg font-bold text-slate-800">📊 Laporan Penjualan</h3>
        <div class="flex items-center gap-2">
          <button v-if="report" @click="print"
            class="text-xs bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg px-2.5 py-1.5">🖨️ Cetak</button>
          <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
        </div>
      </div>
      <div class="flex items-center gap-2 mb-3 no-print">
        <label class="text-xs text-slate-500">Tanggal</label>
        <input v-model="selDate" @change="load" type="date"
          class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-brand-500" />
        <button @click="selDate = new Date().toISOString().slice(0, 10); load()"
          class="text-xs bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg px-2 py-1.5">Hari ini</button>
      </div>

      <!-- Tab metode bayar -->
      <div v-if="report && !loading" class="flex gap-1 mb-3 no-print bg-slate-100 rounded-lg p-1">
        <button @click="tab = 'all'" :class="tab === 'all' ? 'bg-white shadow text-brand-700' : 'text-slate-500'"
          class="flex-1 text-xs font-medium rounded-md py-1.5">Semua</button>
        <button v-for="mt in methodTabs" :key="mt.key" @click="tab = mt.key"
          :class="tab === mt.key ? 'bg-white shadow text-brand-700' : 'text-slate-500'"
          class="flex-1 text-xs font-medium rounded-md py-1.5">{{ mt.label }}</button>
      </div>

      <div v-if="loading" class="text-center text-slate-400 text-sm py-6">Memuat…</div>
      <p v-else-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{{ err }}</p>
      <div v-else class="printable">
        <div class="text-center mb-2 hidden print:block">
          <img src="/asp-logo.png" alt="ASP Sports" class="h-8 mx-auto mb-1" />
          <p class="text-xs font-semibold">Laporan Penjualan per Kategori</p>
        </div>
        <p class="text-xs text-slate-400 mb-3">{{ report.date }} · {{ report.order_count }} transaksi (termasuk DP)<span v-if="tab !== 'all'"> · metode <b class="text-slate-500">{{ methodTabs.find(m => m.key === tab)?.label }}</b></span></p>

        <div v-if="!shownCategories.length" class="text-center text-slate-400 text-sm py-6">
          {{ tab === 'all' ? 'Belum ada uang masuk pada tanggal ini.' : 'Tidak ada penjualan via metode ini.' }}
        </div>
        <div v-else class="space-y-1.5">
          <div v-for="c in shownCategories" :key="c.category"
            class="bg-slate-50 rounded-lg print:bg-transparent print:rounded-none print:border-b print:border-dashed">
            <!-- baris kategori (klik utk buka rincian) -->
            <div class="flex items-center justify-between px-3 py-2.5 print:px-0 print:py-1"
              :class="c.items && c.items.length ? 'cursor-pointer' : ''"
              @click="c.items && c.items.length && toggle(c.category)">
              <div class="flex items-center gap-1.5">
                <span v-if="c.items && c.items.length" class="text-slate-400 text-xs transition-transform no-print"
                  :class="open.has(c.category) ? 'rotate-90' : ''">▸</span>
                <div>
                  <p class="text-sm font-medium text-slate-700">{{ c.category }}</p>
                  <p v-if="c.qty != null" class="text-[11px] text-slate-400">{{ c.qty }} item</p>
                </div>
              </div>
              <span class="font-bold text-brand-700 text-sm">{{ rupiah(c.amount) }}</span>
            </div>
            <!-- rincian item (accordion; di cetak selalu tampil) -->
            <div v-if="c.items && c.items.length"
              :class="[open.has(c.category) ? 'block' : 'hidden', 'print:block']"
              class="px-3 pb-2 pt-0.5 print:px-0 print:pb-1">
              <div v-for="it in c.items" :key="it.name"
                class="flex items-center justify-between py-1 pl-4 border-t border-slate-200/70 print:border-slate-300">
                <span class="text-xs text-slate-500 truncate mr-2">{{ it.name }}<span v-if="it.qty != null" class="text-slate-400"> · {{ it.qty }}×</span></span>
                <span class="text-xs font-medium text-slate-600 whitespace-nowrap">{{ rupiah(it.amount) }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- ringkasan lengkap hanya di tab Semua -->
        <template v-if="tab === 'all'">
        <!-- ringkasan: penjualan kotor → diskon/DP → uang masuk -->
        <div class="border-t mt-3 pt-2 space-y-1 text-sm">
          <div class="flex justify-between px-3 print:px-0">
            <span class="text-slate-600">Penjualan (nilai penuh)</span>
            <span class="font-medium text-slate-700">{{ rupiah(report.gross_total) }}</span>
          </div>
          <div v-if="report.advance_booking_total > 0" class="flex justify-between px-3 print:px-0 text-xs text-slate-400">
            <span>↳ termasuk booking di muka (main tgl lain)</span>
            <span>{{ rupiah(report.advance_booking_total) }}</span>
          </div>
          <div v-if="report.discount_total > 0" class="flex justify-between px-3 print:px-0 text-amber-600">
            <span>Diskon</span><span>− {{ rupiah(report.discount_total) }}</span>
          </div>
          <div v-if="report.unpaid_total > 0" class="flex justify-between px-3 print:px-0 text-amber-600">
            <span>Belum lunas (DP)</span><span>− {{ rupiah(report.unpaid_total) }}</span>
          </div>
          <div v-if="report.paid_other_total > 0" class="flex justify-between px-3 print:px-0 text-slate-400">
            <span>Dibayar hari lain (DP)</span><span>− {{ rupiah(report.paid_other_total) }}</span>
          </div>
        </div>

        <p class="text-xs font-medium text-slate-400 mt-3 mb-1.5">Uang masuk per metode</p>
        <div class="space-y-1">
          <div v-for="m in report.by_method" :key="m.method"
            class="flex items-center justify-between px-3 py-1.5 print:px-0 print:py-0.5">
            <span class="text-sm text-slate-600">{{ m.label }}</span>
            <span class="font-semibold text-sm" :class="m.amount > 0 ? 'text-slate-700' : 'text-slate-400'">{{ rupiah(m.amount) }}</span>
          </div>
        </div>
        </template>

        <div class="flex justify-between items-center border-t mt-3 pt-3">
          <span class="font-semibold text-slate-700">{{ tab === 'all' ? 'Total uang masuk' : `Total ${methodTabs.find(m => m.key === tab)?.label}` }}</span>
          <span class="font-bold text-lg text-emerald-700">{{ rupiah(tab === 'all' ? report.total : methodTotal(tab)) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
