<script setup>
import { ref, onMounted, computed } from 'vue'
import client from '../api/client'

const tab = ref('report')
const year = new Date().getFullYear()
const from = ref(`${year}-01-01`)
const to = ref(new Date().toISOString().slice(0, 10))

const rep = ref(null)
const loadingRep = ref(false)

// beban holding
const hexp = ref({ expenses: [], total: 0, categories: [] })
const loadingHexp = ref(false)
const showForm = ref(false)
const busy = ref(false)
const form = ref({ category: 'Prive', description: '', amount: null, expense_date: to.value })
const toast = ref('')

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2500) }
const isProfit = computed(() => (rep.value?.net_profit ?? 0) >= 0)

async function loadReport() {
  loadingRep.value = true
  try {
    const { data } = await client.get('/financial/management-report', { params: { from: from.value, to: to.value } })
    rep.value = data
  } finally { loadingRep.value = false }
}
async function loadHexp() {
  loadingHexp.value = true
  try {
    const { data } = await client.get('/financial/holding-expenses', { params: { from: from.value, to: to.value } })
    hexp.value = data
  } finally { loadingHexp.value = false }
}
async function saveHexp() {
  if (!form.value.amount || form.value.amount <= 0) { alert('Nominal harus lebih dari 0'); return }
  busy.value = true
  try {
    await client.post('/financial/holding-expenses', form.value)
    showForm.value = false
    form.value = { category: 'Prive', description: '', amount: null, expense_date: to.value }
    await loadHexp(); await loadReport()
    flash('Beban holding tersimpan')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal menyimpan.') } finally { busy.value = false }
}
async function delHexp(e) {
  if (!confirm(`Hapus ${e.code} (${e.category}, ${rupiah(e.amount)})?`)) return
  try { await client.delete(`/financial/holding-expenses/${e.id}`); await loadHexp(); await loadReport(); flash('Dihapus') }
  catch (err) { alert('Gagal menghapus.') }
}
function apply() { loadReport(); if (tab.value === 'holding') loadHexp() }
function switchTab(t) { tab.value = t; if (t === 'holding' && !hexp.value.expenses.length) loadHexp() }

onMounted(loadReport)
</script>

<template>
  <div>
    <div class="flex items-center gap-2 mb-1">
      <h1 class="text-2xl font-bold text-slate-800">Laporan Manajemen</h1>
      <span class="text-xs bg-red-50 text-red-600 px-2 py-0.5 rounded-full font-medium">🔐 Rahasia — HO/Owner</span>
    </div>
    <p class="text-slate-500 mb-5">Konsolidasi seluruh venue + pengeluaran owner (prive, fee direktur, bonus). Tidak terlihat oleh manajer venue.</p>

    <!-- Filter -->
    <div class="bg-white rounded-xl shadow-sm border p-4 mb-5 flex flex-wrap items-end gap-3">
      <div><label class="block text-xs text-slate-500 mb-1">Dari</label>
        <input v-model="from" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <div><label class="block text-xs text-slate-500 mb-1">Sampai</label>
        <input v-model="to" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <button @click="apply" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-5 py-2 font-medium">Terapkan</button>
    </div>

    <!-- Tabs -->
    <div class="border-b mb-5 flex gap-1">
      <button @click="switchTab('report')" :class="tab === 'report' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Laporan</button>
      <button @click="switchTab('holding')" :class="tab === 'holding' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Beban Holding / Owner</button>
    </div>

    <!-- ============ TAB: LAPORAN ============ -->
    <div v-if="tab === 'report'">
      <div v-if="loadingRep" class="text-slate-400">Memuat…</div>
      <template v-else-if="rep">
        <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
          <div class="bg-white rounded-xl shadow-sm border p-5">
            <p class="text-sm text-slate-500">Laba Bisnis (semua venue)</p>
            <p class="text-2xl font-bold mt-1" :class="rep.business.net >= 0 ? 'text-slate-800' : 'text-amber-600'">{{ rupiah(rep.business.net) }}</p>
          </div>
          <div class="bg-white rounded-xl shadow-sm border p-5">
            <p class="text-sm text-slate-500">Beban Holding / Owner</p>
            <p class="text-2xl font-bold text-red-600 mt-1">{{ rupiah(rep.holding.total) }}</p>
          </div>
          <div class="bg-white rounded-xl shadow-sm border p-5 ring-1" :class="isProfit ? 'ring-brand-200' : 'ring-amber-200'">
            <p class="text-sm text-slate-500">{{ isProfit ? 'Laba Bersih Sesungguhnya' : 'Rugi Bersih Sesungguhnya' }}</p>
            <p class="text-2xl font-bold mt-1" :class="isProfit ? 'text-brand-600' : 'text-amber-600'">{{ rupiah(rep.net_profit) }}</p>
          </div>
          <div class="bg-white rounded-xl shadow-sm border p-5">
            <p class="text-sm text-slate-500">Saldo Kas (semua rekening)</p>
            <p class="text-2xl font-bold text-slate-800 mt-1">{{ rupiah(rep.cash.total) }}</p>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <!-- Kinerja per venue -->
          <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
            <h3 class="font-semibold text-slate-700 px-4 py-3 border-b">Kinerja per Venue</h3>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead class="bg-slate-50 text-slate-500 text-left"><tr>
                  <th class="px-4 py-2 font-medium">Venue</th>
                  <th class="px-4 py-2 font-medium text-right">Pendapatan</th>
                  <th class="px-4 py-2 font-medium text-right">Beban</th>
                  <th class="px-4 py-2 font-medium text-right">Laba/Rugi</th>
                </tr></thead>
                <tbody>
                  <tr v-if="!rep.business.by_venue.length"><td colspan="4" class="px-4 py-6 text-center text-slate-400">Belum ada transaksi.</td></tr>
                  <tr v-for="v in rep.business.by_venue" :key="v.venue_id" class="border-t">
                    <td class="px-4 py-2 text-slate-700">{{ v.venue_code }} — {{ v.venue_name }}</td>
                    <td class="px-4 py-2 text-right text-emerald-600">{{ rupiah(v.revenue) }}</td>
                    <td class="px-4 py-2 text-right text-red-600">{{ rupiah(v.expense) }}</td>
                    <td class="px-4 py-2 text-right font-medium" :class="v.net >= 0 ? 'text-slate-700' : 'text-amber-600'">{{ rupiah(v.net) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Beban holding per kategori -->
          <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
            <h3 class="font-semibold text-slate-700 px-4 py-3 border-b">Beban Holding / Owner per Kategori</h3>
            <table class="w-full text-sm">
              <tbody>
                <tr v-if="!rep.holding.by_category.length"><td class="px-4 py-6 text-center text-slate-400">Tidak ada pada periode ini.</td></tr>
                <tr v-for="c in rep.holding.by_category" :key="c.category" class="border-t">
                  <td class="px-4 py-2 text-slate-600">{{ c.category }}</td>
                  <td class="px-4 py-2 text-right font-medium text-red-600">{{ rupiah(c.amount) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </div>

    <!-- ============ TAB: BEBAN HOLDING ============ -->
    <div v-else-if="tab === 'holding'">
      <div class="flex items-center justify-between mb-4">
        <p class="text-sm text-slate-500">Total periode ini: <span class="font-semibold text-red-600">{{ rupiah(hexp.total) }}</span></p>
        <button @click="showForm = !showForm" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Tambah Beban</button>
      </div>

      <!-- Form -->
      <div v-if="showForm" class="bg-white rounded-xl shadow-sm border p-4 mb-5 grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div><label class="block text-xs text-slate-500 mb-1">Kategori</label>
          <select v-model="form.category" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
            <option v-for="c in (hexp.categories.length ? hexp.categories : ['Prive','Fee Direktur','Bonus','Lainnya'])" :key="c" :value="c">{{ c }}</option>
          </select></div>
        <div><label class="block text-xs text-slate-500 mb-1">Tanggal</label>
          <input v-model="form.expense_date" type="date" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
        <div class="sm:col-span-2"><label class="block text-xs text-slate-500 mb-1">Keterangan (opsional)</label>
          <input v-model="form.description" type="text" placeholder="mis. Tarikan owner Juli" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
        <div><label class="block text-xs text-slate-500 mb-1">Nominal (Rp)</label>
          <input v-model.number="form.amount" type="number" min="0" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
        <div class="flex items-end gap-2">
          <button @click="saveHexp" :disabled="busy" class="bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm rounded-lg px-5 py-2 font-medium">Simpan</button>
          <button @click="showForm = false" class="text-slate-500 text-sm px-3 py-2">Batal</button>
        </div>
        <p class="sm:col-span-2 text-xs text-slate-400">Uang keluar dari rekening holding & tercatat di buku besar Kas &amp; Bank.</p>
      </div>

      <!-- List -->
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div v-if="loadingHexp" class="p-6 text-slate-400">Memuat…</div>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-4 py-2 font-medium">Tanggal</th>
              <th class="px-4 py-2 font-medium">Kode</th>
              <th class="px-4 py-2 font-medium">Kategori</th>
              <th class="px-4 py-2 font-medium">Keterangan</th>
              <th class="px-4 py-2 font-medium text-right">Nominal</th>
              <th class="px-4 py-2"></th>
            </tr></thead>
            <tbody>
              <tr v-if="!hexp.expenses.length"><td colspan="6" class="px-4 py-6 text-center text-slate-400">Belum ada beban holding.</td></tr>
              <tr v-for="e in hexp.expenses" :key="e.id" class="border-t">
                <td class="px-4 py-2 text-slate-500">{{ e.expense_date }}</td>
                <td class="px-4 py-2 text-slate-500">{{ e.code }}</td>
                <td class="px-4 py-2 text-slate-700">{{ e.category }}</td>
                <td class="px-4 py-2 text-slate-600">{{ e.description || '—' }}</td>
                <td class="px-4 py-2 text-right font-medium text-red-600">{{ rupiah(e.amount) }}</td>
                <td class="px-4 py-2 text-right"><button @click="delHexp(e)" class="text-red-500 hover:text-red-700 text-xs">Hapus</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Toast -->
    <div v-if="toast" class="fixed bottom-6 right-6 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
