<script setup>
import { ref, onMounted, nextTick, computed } from 'vue'
import client from '../api/client'
import Chart from 'chart.js/auto'
import { parseUTC } from '../utils/datetime'
import { useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'

const auth = useAuthStore()
const toastStore = useToastStore()
function flash(m) { toastStore.show(m) }
const canDeleteShift = computed(() => auth.hasPerm('order.cancel'))
const canReopen = computed(() => ['admin', 'head_office'].includes(auth.user?.role))
const isManager = computed(() => auth.user?.role === 'manager_unit')

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
async function deleteShift(s) {
  if (!window.confirm(`Hapus shift ${s.cashier || ''} (${s.opened_at ? parseUTC(s.opened_at).toLocaleString('id-ID') : ''})?\nHanya bisa kalau shift tak punya transaksi.`)) return
  try {
    await client.delete(`/admin/shifts/${s.id}`)
    await run()
    flash('Shift dihapus')
  } catch (e) {
    alert(e?.response?.data?.message || 'Gagal menghapus shift.')
  }
}
async function reopenShift(s) {
  const reason = window.prompt(
    `Buka kembali shift ${s.cashier || ''} (${s.opened_at ? parseUTC(s.opened_at).toLocaleString('id-ID') : ''})?\n\n` +
    `Shift akan kembali TERBUKA agar bisa dikoreksi (tambah/batalkan transaksi), lalu tutup lagi.\n` +
    `Tulis ALASAN (wajib, tercatat di audit):`)
  if (reason === null) return
  if (!reason.trim()) { alert('Alasan wajib diisi.'); return }
  try {
    const { data } = await client.post(`/admin/shifts/${s.id}/reopen`, { reason: reason.trim() })
    await run()
    flash(data?.message || 'Shift dibuka kembali')
  } catch (e) {
    alert(e?.response?.data?.message || 'Gagal membuka shift.')
  }
}
// ---- Rincian transaksi shift (lihat & edit item) ----
const showSO = ref(false)
const soShift = ref(null)
const soOrders = ref([])
const soLoading = ref(false)
const soSaving = ref(null)   // id order yg sedang disimpan
const statusLabel = { paid: 'Lunas', open: 'Belum Lunas', void: 'Dibatalkan' }
function prepOrder(o) {
  return {
    ...o,
    _prod: o.items.filter((i) => i.item_type === 'product').map((i) => ({ name: i.name, quantity: Number(i.quantity), unit_price: Number(i.unit_price) })),
    _locked: o.items.filter((i) => i.item_type !== 'product'),
    _methods: [...new Set((o.payments || []).filter((p) => p.status === 'paid').map((p) => p.method))].join(', '),
  }
}
async function openShiftOrders(s) {
  soShift.value = s; soOrders.value = []; showSO.value = true; soLoading.value = true
  try {
    const { data } = await client.get(`/admin/shifts/${s.id}/orders`)
    soOrders.value = data.orders.map(prepOrder)
  } catch (e) { alert(e?.response?.data?.message || 'Gagal memuat.') } finally { soLoading.value = false }
}
function soAddLine(o) { o._prod.push({ name: '', quantity: 1, unit_price: null }) }
function soRmLine(o, i) { o._prod.splice(i, 1) }
function soOrderTotal(o) {
  const prod = o._prod.reduce((t, i) => t + (Number(i.quantity) || 0) * (Number(i.unit_price) || 0), 0)
  const locked = o._locked.reduce((t, i) => t + (Number(i.line_total) || 0), 0)
  return prod + locked - (Number(o.discount_amount) || 0)
}
async function saveOrder(o) {
  soSaving.value = o.id
  try {
    const items = o._prod.filter((i) => i.name?.trim() && Number(i.quantity) > 0)
      .map((i) => ({ name: i.name.trim(), quantity: Number(i.quantity), unit_price: Number(i.unit_price) || 0 }))
    await client.put(`/admin/orders/${o.id}/edit-items`, { items })
    // muat ulang daftar + tabel shift
    const { data } = await client.get(`/admin/shifts/${soShift.value.id}/orders`)
    soOrders.value = data.orders.map(prepOrder)
    await run()
    flash('Transaksi dikoreksi')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal menyimpan.') } finally { soSaving.value = null }
}

// ---- Penyesuaian shift cepat (+/- per metode) ----
const showAdj = ref(false)
const adjShift = ref(null)
const adjForm = ref({ cash: null, qris: null, transfer: null, note: '' })
const adjSaving = ref(false)
const adjErr = ref('')
function openAdjust(s) {
  adjShift.value = s
  adjForm.value = { cash: null, qris: null, transfer: null, note: '' }
  adjErr.value = ''
  showAdj.value = true
}
function adjNewTotal(s, field, delta) { return (Number(s?.[field]) || 0) + (Number(delta) || 0) }
async function submitAdjust() {
  const anyVal = ['cash', 'qris', 'transfer'].some((k) => Number(adjForm.value[k]))
  if (!anyVal) { adjErr.value = 'Isi minimal satu nominal (boleh minus).'; return }
  if (!adjForm.value.note.trim()) { adjErr.value = 'Catatan/alasan wajib diisi.'; return }
  adjSaving.value = true; adjErr.value = ''
  try {
    const { data } = await client.post(`/admin/shifts/${adjShift.value.id}/adjust`, {
      cash: Number(adjForm.value.cash) || 0,
      qris: Number(adjForm.value.qris) || 0,
      transfer: Number(adjForm.value.transfer) || 0,
      note: adjForm.value.note.trim(),
    })
    showAdj.value = false
    await run()
    flash(data?.message || 'Penyesuaian tersimpan')
  } catch (e) { adjErr.value = e?.response?.data?.message || 'Gagal.' } finally { adjSaving.value = false }
}

// ---- Entri koreksi back-date ----
const showCorr = ref(false)
const corrShift = ref(null)
const corrForm = ref({ customer_name: '', method: 'cash', items: [] })
const corrSaving = ref(false)
const corrErr = ref('')
const corrProducts = ref([])
const corrTotal = computed(() => corrForm.value.items.reduce((t, i) => t + (Number(i.qty) || 0) * (Number(i.unit_price) || 0), 0))
function newCorrLine() { return { product_id: '', name: '', qty: 1, unit_price: null, deduct_stock: false } }
async function openCorrection(s) {
  corrShift.value = s
  corrForm.value = { customer_name: '', method: 'cash', items: [newCorrLine()] }
  corrErr.value = ''; corrProducts.value = []
  showCorr.value = true
  try {
    const { data } = await client.get('/admin/products', { params: { venue_id: s.venue_id } })
    corrProducts.value = data.products || []
  } catch { corrProducts.value = [] }
}
function onCorrProduct(it) {
  const p = corrProducts.value.find((x) => x.id === it.product_id)
  if (!p) { it.deduct_stock = false; return }   // manual/kosong
  it.name = p.name
  if (it.unit_price == null || it.unit_price === '') it.unit_price = p.effective_price ?? p.price
  it.deduct_stock = !!p.track_stock             // default centang kalau produk pakai stok
}
function corrProductTracked(it) {
  const p = corrProducts.value.find((x) => x.id === it.product_id)
  return !!(p && p.track_stock)
}
function addCorrLine() { corrForm.value.items.push(newCorrLine()) }
function rmCorrLine(i) { corrForm.value.items.splice(i, 1) }
async function submitCorrection() {
  const items = corrForm.value.items.filter((i) => i.name?.trim() && Number(i.qty) > 0)
  if (!items.length) { corrErr.value = 'Isi minimal 1 baris (nama & qty).'; return }
  corrSaving.value = true; corrErr.value = ''
  try {
    const { data } = await client.post(`/admin/shifts/${corrShift.value.id}/correction-entry`, {
      method: corrForm.value.method,
      customer_name: corrForm.value.customer_name || null,
      items: items.map((i) => ({
        name: i.name.trim(), qty: Number(i.qty), unit_price: Number(i.unit_price) || 0,
        product_id: i.product_id || null,
        deduct_stock: !!(i.product_id && i.deduct_stock),
      })),
    })
    showCorr.value = false
    await run()
    flash(data?.message || 'Koreksi ditambahkan')
  } catch (e) { corrErr.value = e?.response?.data?.message || 'Gagal.' } finally { corrSaving.value = false }
}
async function closeShiftAdmin(s) {
  const raw = window.prompt(
    `Tutup shift ${s.cashier || ''}.\n\n` +
    `Masukkan jumlah UANG TUNAI yang dihitung (untuk hitung selisih kas):`,
    String(Number(s.expected_cash) || 0))
  if (raw === null) return
  const counted = Number(raw)
  if (isNaN(counted) || counted < 0) { alert('Nominal tidak valid.'); return }
  try {
    const { data } = await client.post(`/admin/shifts/${s.id}/close`, { counted_cash: counted })
    await run()
    flash(data?.message || 'Shift ditutup')
  } catch (e) {
    alert(e?.response?.data?.message || 'Gagal menutup shift.')
  }
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
// Tab: laporan vs riwayat buka shift
const tab = ref('report')
const reopenLogs = ref([])
const reopenLoading = ref(false)
async function loadReopenLogs() {
  reopenLoading.value = true
  try {
    const params = {}
    if (venueId.value) params.venue_id = venueId.value
    const { data } = await client.get('/admin/shifts/reopen-logs', { params })
    reopenLogs.value = data.logs
  } catch { reopenLogs.value = [] } finally { reopenLoading.value = false }
}
function switchTab(t) { tab.value = t; if (t === 'reopen') loadReopenLogs() }
function venueName(id) { const v = venues.value.find((x) => x.id === id); return v ? v.code : '—' }

onMounted(async () => { await loadVenues(); await run() })
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-800 mb-1">Laporan</h1>
    <p class="text-slate-500 mb-5">Penjualan dan rekonsiliasi shift.</p>

    <!-- Tabs -->
    <div v-if="canReopen" class="flex gap-1 border-b border-slate-200 mb-5">
      <button @click="switchTab('report')" :class="tab === 'report' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Laporan</button>
      <button @click="switchTab('reopen')" :class="tab === 'reopen' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">↻ Riwayat Buka Shift</button>
    </div>

    <!-- Filter -->
    <div v-show="tab === 'report'" class="bg-white rounded-xl shadow-sm border p-4 mb-5 flex flex-wrap items-end gap-3">
      <div><label class="block text-xs text-slate-500 mb-1">Dari</label>
        <input v-model="from" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <button @click="to = from" type="button" title="Samakan: Sampai = Dari (satu hari)"
        class="h-[38px] px-2.5 rounded-lg border border-slate-300 text-slate-500 hover:bg-brand-50 hover:text-brand-600 hover:border-brand-300 text-sm">⇥</button>
      <div><label class="block text-xs text-slate-500 mb-1">Sampai</label>
        <input v-model="to" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <div v-if="!isManager"><label class="block text-xs text-slate-500 mb-1">Venue</label>
        <select v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua venue</option>
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select></div>
      <button @click="run" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-5 py-2 font-medium">Terapkan</button>
    </div>

    <div v-if="tab === 'report' && loading" class="text-slate-400">Memuat…</div>

    <template v-else-if="tab === 'report' && sales">
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

      <!-- Konsinyasi vs Milik Sendiri -->
      <div v-if="sales.consignment && (sales.consignment.own_revenue || sales.consignment.consignment_revenue)" class="bg-white rounded-xl shadow-sm border p-5 mb-5">
        <h3 class="font-semibold text-slate-700 mb-3">Milik Sendiri vs Konsinyasi</h3>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <p class="text-xs text-slate-500">Penjualan Milik Sendiri</p>
            <p class="text-lg font-bold text-slate-800">{{ rupiah(sales.consignment.own_revenue) }}</p>
          </div>
          <div>
            <p class="text-xs text-slate-500">Penjualan Konsinyasi</p>
            <p class="text-lg font-bold text-slate-800">{{ rupiah(sales.consignment.consignment_revenue) }}</p>
          </div>
          <div>
            <p class="text-xs text-slate-500">Estimasi ke Supplier</p>
            <p class="text-lg font-bold text-amber-600">{{ rupiah(sales.consignment.consignment_owed) }}</p>
          </div>
          <div>
            <p class="text-xs text-slate-500">Estimasi Margin Konsinyasi</p>
            <p class="text-lg font-bold text-emerald-600">{{ rupiah(sales.consignment.consignment_margin) }}</p>
          </div>
        </div>
        <p class="text-xs text-slate-400 mt-3">"Estimasi ke Supplier" &amp; "Estimasi Margin" dihitung dari harga bagi hasil per produk — nilai pasti dibayar lewat menu Procurement → tab Konsinyasi.</p>
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
              <th class="px-4 py-2 font-medium text-right">Transfer</th>
              <th class="px-4 py-2 font-medium text-right">Seharusnya</th>
              <th class="px-4 py-2 font-medium text-right">Dihitung</th>
              <th class="px-4 py-2 font-medium text-right">Selisih</th>
              <th class="px-4 py-2 font-medium text-center">Status</th>
              <th v-if="canDeleteShift || canReopen" class="px-4 py-2"></th>
            </tr></thead>
            <tbody>
              <tr v-if="!shifts.length"><td :colspan="(canDeleteShift || canReopen) ? 10 : 9" class="px-4 py-6 text-center text-slate-400">Tidak ada shift.</td></tr>
              <tr v-for="s in shifts" :key="s.id" class="border-t">
                <td class="px-4 py-2 text-slate-700">{{ s.cashier || '—' }}</td>
                <td class="px-4 py-2 text-slate-500">{{ s.opened_at ? parseUTC(s.opened_at).toLocaleString('id-ID') : '—' }}</td>
                <td class="px-4 py-2 text-right">{{ rupiah(s.total_cash_sales) }}</td>
                <td class="px-4 py-2 text-right">{{ rupiah(s.total_qris_sales) }}</td>
                <td class="px-4 py-2 text-right">{{ rupiah(s.total_transfer_sales) }}</td>
                <td class="px-4 py-2 text-right">{{ rupiah(s.expected_cash) }}</td>
                <td class="px-4 py-2 text-right">{{ s.counted_cash != null ? rupiah(s.counted_cash) : '—' }}</td>
                <td class="px-4 py-2 text-right font-medium" :class="s.cash_variance === 0 ? 'text-emerald-600' : (s.cash_variance == null ? 'text-slate-400' : 'text-red-600')">
                  {{ s.cash_variance != null ? rupiah(s.cash_variance) : '—' }}
                </td>
                <td class="px-4 py-2 text-center whitespace-nowrap">
                  <span v-if="s.status === 'open'" class="text-xs rounded-full px-2 py-0.5 bg-amber-100 text-amber-700">Terbuka</span>
                  <span v-else class="text-xs rounded-full px-2 py-0.5 bg-slate-100 text-slate-500">Tertutup</span>
                  <span v-if="s.reopened_count > 0" :title="`Pernah dibuka kembali ${s.reopened_count}×`" class="ml-1 text-xs text-brand-600">↻{{ s.reopened_count }}</span>
                  <span v-if="s.deposited" title="Sudah disetor" class="ml-1 text-xs text-emerald-600">💰</span>
                </td>
                <td v-if="canDeleteShift || canReopen" class="px-4 py-2 text-right whitespace-nowrap">
                  <button v-if="canReopen" @click="openShiftOrders(s)" class="text-slate-600 text-xs hover:underline">📋 Rincian</button>
                  <button v-if="canReopen && !s.deposited" @click="openAdjust(s)" class="text-indigo-600 text-xs hover:underline ml-3">⇅ Sesuaikan</button>
                  <button v-if="canReopen && s.status === 'closed' && !s.deposited" @click="reopenShift(s)" class="text-brand-600 text-xs hover:underline ml-3">↻ Buka Kembali</button>
                  <button v-if="canReopen && s.status === 'open'" @click="openCorrection(s)" class="text-brand-600 text-xs hover:underline">+ Koreksi</button>
                  <button v-if="canReopen && s.status === 'open'" @click="closeShiftAdmin(s)" class="text-emerald-600 text-xs hover:underline ml-3">Tutup</button>
                  <button v-if="canDeleteShift" @click="deleteShift(s)" class="text-red-500 text-xs hover:underline ml-3">Hapus</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- ===== Riwayat Buka Shift (audit) ===== -->
    <div v-show="tab === 'reopen'">
      <div class="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5 text-sm text-amber-800 mb-4">
        Jejak setiap shift yang <b>dibuka kembali</b> oleh Admin/HO untuk dikoreksi — beserta alasan & kondisi kas sebelum dibuka. Filter venue mengikuti pilihan di tab Laporan.
      </div>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-4 py-3 font-medium">Waktu Dibuka</th>
              <th class="px-4 py-3 font-medium">Venue</th>
              <th class="px-4 py-3 font-medium">Shift ID</th>
              <th class="px-4 py-3 font-medium">Dibuka oleh</th>
              <th class="px-4 py-3 font-medium text-right">Selisih (sblm)</th>
              <th class="px-4 py-3 font-medium">Alasan</th>
            </tr></thead>
            <tbody>
              <tr v-if="reopenLoading"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
              <tr v-else-if="!reopenLogs.length"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Belum ada shift yang dibuka kembali.</td></tr>
              <tr v-for="l in reopenLogs" :key="l.id" class="border-t hover:bg-slate-50">
                <td class="px-4 py-3 text-slate-500 whitespace-nowrap">{{ l.reopened_at ? parseUTC(l.reopened_at).toLocaleString('id-ID') : '—' }}</td>
                <td class="px-4 py-3 text-slate-600">{{ venueName(l.venue_id) }}</td>
                <td class="px-4 py-3 font-mono text-xs text-slate-500">#{{ l.shift_id }}</td>
                <td class="px-4 py-3 text-slate-600">{{ l.reopened_by_name || '—' }}</td>
                <td class="px-4 py-3 text-right font-medium" :class="l.variance_before == null ? 'text-slate-300' : (l.variance_before === 0 ? 'text-emerald-600' : 'text-red-600')">{{ l.variance_before != null ? rupiah(l.variance_before) : '—' }}</td>
                <td class="px-4 py-3 text-slate-700 max-w-md">{{ l.reason }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Modal: Rincian transaksi shift (edit item) -->
    <div v-if="showSO" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="showSO = false">
      <div class="bg-white w-full max-w-3xl rounded-2xl p-5 max-h-[92vh] overflow-auto">
        <div class="flex justify-between items-center mb-1">
          <h3 class="text-lg font-bold text-slate-800">Rincian Transaksi Shift</h3>
          <button @click="showSO = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <p class="text-xs text-slate-500 mb-3">{{ soShift?.cashier || '—' }} · {{ soShift && soShift.opened_at ? parseUTC(soShift.opened_at).toLocaleString('id-ID') : '—' }} · {{ soOrders.length }} transaksi</p>
        <div class="bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-600 mb-3">
          Edit langsung nama/qty/harga item <b>produk</b>. Total order, pembayaran, & kas shift menyesuaikan otomatis (tanggal transaksi dipertahankan). Item booking/tiket dikunci. <b>Stok tidak otomatis disesuaikan.</b>
        </div>
        <div v-if="soLoading" class="text-center text-slate-400 py-8">Memuat…</div>
        <div v-else-if="!soOrders.length" class="text-center text-slate-400 py-8">Tidak ada transaksi di shift ini.</div>
        <div v-else class="space-y-3">
          <div v-for="o in soOrders" :key="o.id" class="border border-slate-200 rounded-xl p-3">
            <div class="flex justify-between items-center mb-2">
              <div>
                <span class="font-mono text-xs text-slate-500">{{ o.order_number }}</span>
                <span class="ml-2 text-xs rounded-full px-2 py-0.5" :class="o.status === 'paid' ? 'bg-emerald-100 text-emerald-700' : (o.status === 'void' ? 'bg-red-100 text-red-600' : 'bg-amber-100 text-amber-700')">{{ statusLabel[o.status] || o.status }}</span>
                <span v-if="o._methods" class="ml-2 text-xs text-slate-400 capitalize">{{ o._methods }}</span>
              </div>
              <span class="text-xs text-slate-400">{{ o.customer_name || '' }}</span>
            </div>
            <!-- item terkunci (booking/tiket/rental) -->
            <div v-for="lk in o._locked" :key="'lk'+lk.id" class="flex items-center gap-2 text-sm text-slate-500 mb-1">
              <span class="flex-1">🔒 {{ lk.name }} <span class="text-xs text-slate-400">({{ lk.item_type }})</span></span>
              <span>{{ lk.quantity }} ×</span>
              <span class="w-24 text-right">{{ rupiah(lk.unit_price) }}</span>
              <span class="w-24 text-right font-medium">{{ rupiah(lk.line_total) }}</span>
            </div>
            <!-- item produk yang bisa diedit -->
            <div v-for="(it, i) in o._prod" :key="i" class="flex items-center gap-2 mb-1.5">
              <input v-model="it.name" placeholder="Nama item" class="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none" />
              <input v-model.number="it.quantity" type="number" min="1" class="w-14 rounded-lg border border-slate-300 px-2 py-1.5 text-sm text-right outline-none" />
              <span class="text-slate-400 text-xs">×</span>
              <input v-model.number="it.unit_price" type="number" placeholder="Harga" class="w-28 rounded-lg border border-slate-300 px-2 py-1.5 text-sm text-right outline-none" />
              <span class="w-24 text-right text-sm text-slate-500">{{ rupiah((Number(it.quantity)||0)*(Number(it.unit_price)||0)) }}</span>
              <button @click="soRmLine(o, i)" class="text-red-400 px-1">✕</button>
            </div>
            <div class="flex items-center justify-between mt-2">
              <button @click="soAddLine(o)" class="text-brand-600 text-xs hover:underline">+ item</button>
              <div class="flex items-center gap-3">
                <span class="text-sm">Total baru: <b class="text-brand-700">{{ rupiah(soOrderTotal(o)) }}</b></span>
                <button @click="saveOrder(o)" :disabled="soSaving === o.id || o.status === 'void'" class="bg-brand-600 hover:bg-brand-700 text-white text-xs rounded-lg px-3 py-1.5 font-medium disabled:opacity-50">{{ soSaving === o.id ? 'Menyimpan…' : 'Simpan' }}</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Penyesuaian shift cepat -->
    <div v-if="showAdj" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="showAdj = false">
      <div class="bg-white w-full max-w-md rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-center mb-1">
          <h3 class="text-lg font-bold text-slate-800">Sesuaikan Shift</h3>
          <button @click="showAdj = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <p class="text-xs text-slate-500 mb-3">{{ adjShift?.cashier || '—' }} · {{ adjShift && adjShift.opened_at ? parseUTC(adjShift.opened_at).toLocaleDateString('id-ID') : '—' }}</p>
        <div class="bg-indigo-50 border border-indigo-200 rounded-lg px-3 py-2 text-xs text-indigo-800 mb-3">
          Isi <b>+/‑ per metode</b> (boleh minus untuk mengurangi). Dicatat sbg penyesuaian back-date sehingga <b>Laporan Shift & Laporan Penjualan tetap cocok</b> dan ter-audit.
        </div>
        <div class="space-y-2 mb-3">
          <div v-for="m in [['cash','Tunai (Cash)','total_cash_sales'],['qris','QRIS','total_qris_sales'],['transfer','Transfer','total_transfer_sales']]" :key="m[0]" class="flex items-center gap-2">
            <label class="w-28 text-sm text-slate-600">{{ m[1] }}</label>
            <input v-model.number="adjForm[m[0]]" type="number" placeholder="0 (± )" class="w-32 rounded-lg border border-slate-300 px-2 py-1.5 text-sm text-right outline-none focus:border-brand-500" />
            <span class="text-xs text-slate-400">→ {{ rupiah(adjNewTotal(adjShift, m[2], adjForm[m[0]])) }}</span>
          </div>
        </div>
        <label class="block text-xs text-slate-500 mb-1">Catatan / alasan (wajib)</label>
        <textarea v-model="adjForm.note" rows="2" placeholder="mis. koreksi salah metode bayar / lupa input tunai" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500 mb-3"></textarea>
        <p v-if="adjErr" class="text-sm text-red-600 mb-2">{{ adjErr }}</p>
        <button @click="submitAdjust" :disabled="adjSaving" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">{{ adjSaving ? 'Menyimpan…' : 'Simpan Penyesuaian' }}</button>
      </div>
    </div>

    <!-- Modal: Entri Koreksi back-date -->
    <div v-if="showCorr" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="showCorr = false">
      <div class="bg-white w-full max-w-lg rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-center mb-1">
          <h3 class="text-lg font-bold text-slate-800">Tambah Transaksi Koreksi</h3>
          <button @click="showCorr = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <div class="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-800 mb-3">
          Transaksi ini dicatat dengan <b>tanggal = tanggal shift</b> ({{ corrShift && corrShift.opened_at ? parseUTC(corrShift.opened_at).toLocaleDateString('id-ID') : '—' }}), bukan hari ini — supaya Laporan Penjualan & Laporan Shift konsisten. Langsung berstatus lunas & masuk kas shift.
        </div>
        <label class="block text-xs text-slate-500 mb-1">Nama pelanggan (opsional)</label>
        <input v-model="corrForm.customer_name" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500 mb-3" placeholder="—" />
        <label class="block text-xs text-slate-500 mb-1">Metode bayar</label>
        <select v-model="corrForm.method" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500 mb-3">
          <option value="cash">Tunai (Cash)</option>
          <option value="qris">QRIS</option>
          <option value="transfer">Transfer</option>
        </select>
        <p class="text-xs font-medium text-slate-500 mb-1">Rincian</p>
        <div v-for="(it, i) in corrForm.items" :key="i" class="border border-slate-200 rounded-lg p-2 mb-2">
          <div class="flex gap-2 mb-1.5">
            <select v-model="it.product_id" @change="onCorrProduct(it)" class="w-40 rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none">
              <option value="">— manual —</option>
              <option v-for="p in corrProducts" :key="p.id" :value="p.id">{{ p.name }}<span v-if="p.track_stock"> (stok {{ p.stock_qty }})</span></option>
            </select>
            <input v-model="it.name" placeholder="Nama item" class="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none" />
            <button @click="rmCorrLine(i)" class="text-red-400 px-1">✕</button>
          </div>
          <div class="flex gap-2 items-center">
            <input v-model.number="it.qty" type="number" min="1" placeholder="Qty" class="w-16 rounded-lg border border-slate-300 px-2 py-1.5 text-sm text-right outline-none" />
            <input v-model.number="it.unit_price" type="number" placeholder="Harga" class="w-28 rounded-lg border border-slate-300 px-2 py-1.5 text-sm text-right outline-none" />
            <span class="text-xs text-slate-400 ml-1">= {{ rupiah((Number(it.qty)||0) * (Number(it.unit_price)||0)) }}</span>
            <label v-if="corrProductTracked(it)" class="ml-auto flex items-center gap-1 text-xs text-slate-600 cursor-pointer">
              <input v-model="it.deduct_stock" type="checkbox" class="rounded" /> Kurangi stok
            </label>
          </div>
        </div>
        <button @click="addCorrLine" class="text-brand-600 text-sm mb-2">+ baris</button>
        <p class="text-[11px] text-slate-400 mb-3">Centang <b>Kurangi stok</b> jika barang benar-benar keluar (belum terpotong di POS). Baris manual tanpa produk tidak memengaruhi stok.</p>
        <div class="flex justify-between font-semibold mb-3"><span>Total</span><span class="text-brand-700">{{ rupiah(corrTotal) }}</span></div>
        <p v-if="corrErr" class="text-sm text-red-600 mb-2">{{ corrErr }}</p>
        <button @click="submitCorrection" :disabled="corrSaving || !corrTotal" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">{{ corrSaving ? 'Menyimpan…' : 'Simpan Koreksi' }}</button>
      </div>
    </div>
  </div>
</template>
