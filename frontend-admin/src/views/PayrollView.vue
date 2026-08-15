<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'

const auth = useAuthStore()
const route = useRoute()
const isManager = computed(() => auth.user?.role === 'manager_unit')
const isApprover = computed(() => ['admin', 'head_office'].includes(auth.user?.role))
const canRevert = computed(() => auth.hasPerm('payroll.approve'))

const venues = ref([])
const venueId = ref('')
const now = new Date()
const period = ref(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
const runs = ref([])
const loading = ref(false)
const detail = ref(null)
const busy = ref(false)
const toastStore = useToastStore()

function flash(m) { toastStore.show(m) }
function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function ym() { const [y, m] = period.value.split('-'); return { period_year: +y, period_month: +m } }
const MONTHS = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
const statusMap = { draft: ['Draft', 'bg-slate-100 text-slate-600'], submitted: ['Menunggu', 'bg-amber-100 text-amber-700'], approved: ['Disetujui', 'bg-blue-100 text-blue-700'], paid: ['Dibayar', 'bg-emerald-100 text-emerald-700'], rejected: ['Ditolak', 'bg-red-100 text-red-600'] }
const editable = computed(() => detail.value && ['draft', 'submitted'].includes(detail.value.status))

const accounts = ref([])
const sourceAccount = ref('')
const transferAmount = ref(null)
watch(detail, (d) => { transferAmount.value = d?.total_net ?? null })
async function loadVenues() {
  const { data } = await client.get('/venues')
  venues.value = data.venues
  if (isApprover.value) {
    try {
      const { data: acc } = await client.get('/treasury/accounts')
      accounts.value = acc.accounts
      sourceAccount.value = acc.accounts.find((a) => a.type === 'holding')?.id || acc.accounts[0]?.id || ''
    } catch (_) { /* treasury belum disetup */ }
  }
}
async function loadRuns() {
  loading.value = true
  const params = {}
  if (!isManager.value && venueId.value) params.venue_id = venueId.value
  try { const { data } = await client.get('/payroll/runs', { params }); runs.value = data.runs }
  finally { loading.value = false }
}
onMounted(async () => { await loadVenues(); await loadRuns(); if (tab.value === 'lembur') loadOvertime() })
watch([venueId], loadRuns)

// ---- Tab Lembur (terpisah — pencatatan manual + approval, belum masuk hitungan gaji) ----
const tab = ref(route.query.tab === 'lembur' ? 'lembur' : 'payroll') // 'payroll' | 'lembur'
const otRows = ref([])
const otRun = ref({ status: 'draft' })
const otLoading = ref(false)
const otSaving = ref(false)
const otBusy = ref(false)
const canEditOt = computed(() => auth.hasPerm('payroll.generate'))
const otEditable = computed(() => ['draft', 'rejected'].includes(otRun.value?.status || 'draft') && canEditOt.value)
const otTotal = computed(() => otRows.value.reduce((s, r) => s + (Number(r.amount) || 0), 0))
function otVenue() { return isManager.value ? auth.user?.venue_id : venueId.value }
async function loadOvertime() {
  const vid = otVenue()
  if (!vid) { otRows.value = []; otRun.value = { status: 'draft' }; return }
  otLoading.value = true
  const { period_year, period_month } = ym()
  try {
    const { data } = await client.get('/payroll/overtime', { params: { venue_id: vid, year: period_year, month: period_month } })
    otRows.value = data.items
    otRun.value = data.run || { status: 'draft' }
  } catch (e) { otRows.value = []; otRun.value = { status: 'draft' } } finally { otLoading.value = false }
}
async function saveAllOvertime() {
  const vid = otVenue()
  if (!vid || !otRows.value.length) return
  otSaving.value = true
  const { period_year, period_month } = ym()
  try {
    const { data } = await client.put('/payroll/overtime/bulk', {
      venue_id: vid, period_year, period_month,
      items: otRows.value.map((r) => ({ employee_id: r.employee_id, amount: Number(r.amount) || 0, note: r.note || null })),
    })
    if (data.run) otRun.value = data.run
    flash(`Lembur tersimpan (${data.saved} karyawan)`)
  } catch (e) { alert(e?.response?.data?.message || 'Gagal menyimpan.') } finally { otSaving.value = false }
}
async function otAction(action, extra = {}) {
  const vid = otVenue()
  if (!vid) return
  otBusy.value = true
  const { period_year, period_month } = ym()
  try {
    const { data } = await client.post(`/payroll/overtime/${action}`, { venue_id: vid, period_year, period_month, ...extra })
    if (data.run) otRun.value = data.run
    await loadOvertime()
    flash('Berhasil')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { otBusy.value = false }
}
function submitOvertime() {
  if (!window.confirm('Ajukan lembur periode ini ke HO? Setelah diajukan tidak bisa diubah sampai ditinjau.')) return
  otAction('submit')
}
function rejectOvertime() { const reason = prompt('Alasan penolakan:'); if (reason !== null) otAction('reject', { reason }) }
// muat data lembur saat pindah ke tab-nya / ganti venue-periode saat di tab itu
watch(tab, (t) => { if (t === 'lembur') loadOvertime() })
watch([venueId, period], () => { if (tab.value === 'lembur') loadOvertime() })

async function generate() {
  if (!isManager.value && !venueId.value) { alert('Pilih venue dulu (bukan "Semua venue") untuk generate gaji.'); return }
  busy.value = true
  try {
    const payload = ym()
    if (!isManager.value) payload.venue_id = venueId.value
    const { data } = await client.post('/payroll/runs', payload)
    await loadRuns()
    detail.value = data.run
    flash('Payroll digenerate')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
async function openDetail(r) { const { data } = await client.get(`/payroll/runs/${r.id}`); detail.value = data.run }
async function saveItem(it) {
  try {
    const { data } = await client.put(`/payroll/items/${it.id}`, { allowance: it.allowance, other_deduction: it.other_deduction, note: it.note })
    it.net_salary = data.item.net_salary; detail.value.total_net = data.total_net
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') }
}
async function act(action, extra = {}) {
  busy.value = true
  try { await client.post(`/payroll/runs/${detail.value.id}/${action}`, extra); const { data } = await client.get(`/payroll/runs/${detail.value.id}`); detail.value = data.run; await loadRuns(); flash('Berhasil') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
function doReject() { const reason = prompt('Alasan penolakan:'); if (reason !== null) act('reject', { reason }) }

async function revertRun() {
  const warn = detail.value.status === 'paid'
    ? 'Ini akan membalikkan pembayaran (uang masuk lagi ke Kas & Bank) dan mengembalikan potongan kasbon karyawan. Lanjutkan?'
    : 'Kembalikan status payroll ke Draft?'
  if (!window.confirm(warn)) return
  busy.value = true
  try {
    await client.post(`/payroll/runs/${detail.value.id}/revert`)
    const { data } = await client.get(`/payroll/runs/${detail.value.id}`); detail.value = data.run
    await loadRuns(); flash('Pengajuan dibatalkan — kembali ke Draft')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal membatalkan.') } finally { busy.value = false }
}
const canDeleteRun = (r) => ['draft', 'submitted', 'approved', 'rejected'].includes(r.status)
async function removeRun(r, ev) {
  ev?.stopPropagation()
  if (!window.confirm(`Hapus payroll ${r.code}?`)) return
  try {
    await client.delete(`/payroll/runs/${r.id}`)
    if (detail.value?.id === r.id) detail.value = null
    await loadRuns(); flash('Payroll dihapus')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal menghapus.') }
}

const uploadInput = ref(null)
const uploading = ref(false)
function triggerUpload() { uploadInput.value?.click() }
async function onUpload(e) {
  const file = e.target.files[0]
  e.target.value = ''
  if (!file || !detail.value) return
  uploading.value = true
  try {
    const fd = new FormData(); fd.append('file', file)
    await client.post(`/payroll/runs/${detail.value.id}/attachment`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    const { data } = await client.get(`/payroll/runs/${detail.value.id}`); detail.value = data.run
    flash('Data diunggah')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal mengunggah.') } finally { uploading.value = false }
}

// CSV transfer bank — muncul otomatis begitu payroll disetujui (approved/paid)
function downloadTransferCsv() {
  const r = detail.value
  const rows = [
    ['no_rekening', 'nama_karyawan', 'nominal'],
    ...r.items.map((it) => [it.bank_account || '', (it.employee_name || '').toUpperCase(), it.net_salary]),
  ]
  const csv = rows.map((row) => row.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\r\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `transfer-${r.code}.csv`; a.click()
  URL.revokeObjectURL(url)
}
async function viewAtt(a) { const res = await client.get(`/payroll/attachments/${a.id}`, { responseType: 'blob' }); window.open(URL.createObjectURL(res.data), '_blank') }

function slip(it) {
  const r = detail.value
  const venue = venues.value.find((v) => v.id === r.venue_id)
  const rows = [
    ['Gaji pokok', it.base_salary], ['Tunjangan', it.allowance],
    ['Potongan kasbon', -it.kasbon_deduction], ['Potongan lain', -it.other_deduction],
  ]
  const html = `<html><head><title>Slip ${it.employee_name}</title><style>
    body{font-family:sans-serif;max-width:400px;margin:20px auto;color:#111;font-size:14px}
    h2{margin:0}.muted{color:#666;font-size:12px}hr{border:none;border-top:1px dashed #ccc;margin:10px 0}
    .row{display:flex;justify-content:space-between;padding:2px 0}.net{font-weight:bold;font-size:16px}
    </style></head><body>
    <h2>ASP SPORTS</h2><p class="muted">${venue ? venue.name : ''} · Slip Gaji ${MONTHS[r.period_month]} ${r.period_year}</p><hr>
    <div class="row"><b>${it.employee_name}</b><span>${it.position || ''}</span></div>
    <p class="muted">${it.bank_name || ''} ${it.bank_account || ''}</p><hr>
    ${rows.map((x) => `<div class="row"><span>${x[0]}</span><span>${x[1] < 0 ? '-' : ''}Rp ${Math.abs(x[1]).toLocaleString('id-ID')}</span></div>`).join('')}
    <hr><div class="row net"><span>GAJI BERSIH</span><span>Rp ${Number(it.net_salary).toLocaleString('id-ID')}</span></div>
    <hr><p class="muted">Status: ${statusMap[r.status][0]}</p>
    <script>window.onload=function(){window.print()}<\/script></body></html>`
  const w = window.open('', '_blank'); w.document.write(html); w.document.close()
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-5">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">Payroll</h1>
        <p class="text-slate-500 mt-1">Gaji karyawan — potong kasbon otomatis, approval, & slip.</p>
      </div>
      <div class="flex gap-2 items-center">
        <select v-if="!isManager" v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua venue</option>
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select>
        <input v-model="period" type="month" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
        <button v-if="tab === 'payroll'" @click="generate" :disabled="busy || (!isManager && !venueId)" :title="(!isManager && !venueId) ? 'Pilih venue dulu (bukan Semua venue)' : ''" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">Generate Gaji</button>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 mb-4 border-b">
      <button @click="tab = 'payroll'" :class="tab === 'payroll' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Payroll</button>
      <button @click="tab = 'lembur'" :class="tab === 'lembur' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Lembur</button>
    </div>

    <p v-if="tab === 'payroll' && !isManager && !venueId" class="text-xs text-amber-600 -mt-1 mb-3">Pilih venue tertentu (bukan "Semua venue") untuk bisa generate gaji.</p>

    <!-- ================= TAB PAYROLL ================= -->
    <div v-show="tab === 'payroll'" class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-3 font-medium">Kode</th>
            <th v-if="!isManager" class="px-4 py-3 font-medium">Venue</th>
            <th class="px-4 py-3 font-medium">Periode</th>
            <th class="px-4 py-3 font-medium text-center">Karyawan</th><th class="px-4 py-3 font-medium text-right">Total Net</th>
            <th class="px-4 py-3 font-medium text-center">Status</th><th class="px-4 py-3"></th>
          </tr></thead>
          <tbody>
            <tr v-if="loading"><td colspan="7" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!runs.length"><td colspan="7" class="px-4 py-8 text-center text-slate-400">Belum ada payroll. Klik "Generate Gaji".</td></tr>
            <tr v-for="r in runs" :key="r.id" @click="openDetail(r)" class="border-t hover:bg-slate-50 cursor-pointer">
              <td class="px-4 py-3 font-mono text-xs text-slate-500">{{ r.code }}</td>
              <td v-if="!isManager" class="px-4 py-3 text-slate-600">{{ venues.find(v=>v.id===r.venue_id)?.code || '—' }}</td>
              <td class="px-4 py-3 text-slate-600">{{ MONTHS[r.period_month] }} {{ r.period_year }}</td>
              <td class="px-4 py-3 text-center">{{ r.employee_count }}</td>
              <td class="px-4 py-3 text-right font-medium">{{ rupiah(r.total_net) }}</td>
              <td class="px-4 py-3 text-center"><span :class="statusMap[r.status]?.[1]" class="text-xs rounded-full px-2 py-0.5">{{ statusMap[r.status]?.[0] }}</span></td>
              <td class="px-4 py-3 text-right text-sm whitespace-nowrap">
                <span class="text-brand-600">Detail</span>
                <button v-if="canDeleteRun(r)" @click="removeRun(r, $event)" class="text-red-500 hover:underline ml-3">Hapus</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ================= TAB LEMBUR ================= -->
    <div v-show="tab === 'lembur'">
      <p v-if="!isManager && !venueId" class="text-sm text-amber-600 bg-amber-50 rounded-lg px-4 py-3">
        Pilih venue tertentu (bukan "Semua venue") untuk menampilkan karyawan.
      </p>
      <div v-else class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="flex items-center justify-between flex-wrap gap-3 px-4 py-3 border-b bg-slate-50">
          <div class="flex items-center gap-2">
            <p class="text-sm text-slate-500">Lembur — {{ MONTHS[ym().period_month] }} {{ ym().period_year }} (Rupiah)</p>
            <span :class="statusMap[otRun.status]?.[1] || 'bg-slate-100 text-slate-600'" class="text-xs rounded-full px-2 py-0.5">{{ statusMap[otRun.status]?.[0] || 'Draft' }}</span>
          </div>
          <div class="flex items-center gap-3">
            <p class="text-sm font-semibold text-slate-700">Total: {{ rupiah(otTotal) }}</p>
            <!-- Manajer/unit: simpan + ajukan (saat draft/ditolak) -->
            <template v-if="otEditable">
              <button @click="saveAllOvertime" :disabled="otSaving || !otRows.length"
                class="bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">
                {{ otSaving ? 'Menyimpan…' : 'Simpan Semua' }}
              </button>
              <button @click="submitOvertime" :disabled="otBusy || !otTotal"
                :title="!otTotal ? 'Isi & simpan nilai lembur dulu' : ''"
                class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">
                Ajukan ke HO
              </button>
            </template>
            <!-- HO: setujui / tolak (saat submitted) -->
            <template v-else-if="otRun.status === 'submitted' && isApprover">
              <button @click="otAction('approve')" :disabled="otBusy" class="bg-emerald-600 hover:bg-emerald-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">Setujui</button>
              <button @click="rejectOvertime" :disabled="otBusy" class="bg-red-600 hover:bg-red-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">Tolak</button>
            </template>
            <span v-else-if="otRun.status === 'submitted'" class="text-sm text-amber-600">Menunggu persetujuan HO</span>
          </div>
        </div>

        <p v-if="otRun.status === 'rejected' && otRun.rejection_reason" class="text-sm text-red-600 bg-red-50 px-4 py-2">
          Ditolak HO: {{ otRun.rejection_reason }}
        </p>

        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-4 py-3 font-medium">Karyawan</th>
              <th class="px-4 py-3 font-medium">Jabatan</th>
              <th class="px-4 py-3 font-medium text-right">Nilai Lembur (Rp)</th>
              <th class="px-4 py-3 font-medium">Catatan</th>
            </tr></thead>
            <tbody>
              <tr v-if="otLoading"><td colspan="4" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
              <tr v-else-if="!otRows.length"><td colspan="4" class="px-4 py-8 text-center text-slate-400">Tidak ada karyawan aktif di venue ini.</td></tr>
              <tr v-for="row in otRows" :key="row.employee_id" class="border-t">
                <td class="px-4 py-2.5 text-slate-700">{{ row.employee_name }}</td>
                <td class="px-4 py-2.5 text-slate-500 text-xs">{{ row.position || '—' }}</td>
                <td class="px-4 py-2 text-right">
                  <input v-model.number="row.amount" type="number" min="0" step="1000" :disabled="!otEditable"
                    class="w-32 text-right rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-500" />
                </td>
                <td class="px-4 py-2">
                  <input v-model="row.note" type="text" placeholder="opsional" :disabled="!otEditable"
                    class="w-full min-w-[8rem] rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-500" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Detail -->
    <div v-if="detail" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="detail = null">
      <div class="bg-white w-full max-w-3xl rounded-2xl p-5 max-h-[92vh] overflow-auto">
        <div class="flex justify-between items-start mb-3">
          <div><h3 class="text-lg font-bold text-slate-800">{{ detail.code }}</h3><p class="text-sm text-slate-500">{{ MONTHS[detail.period_month] }} {{ detail.period_year }}</p></div>
          <div class="flex items-center gap-2">
            <button v-if="isApprover && ['approved', 'paid'].includes(detail.status)" @click="downloadTransferCsv" title="Unduh CSV Transfer Bank" class="text-emerald-600 hover:text-emerald-700 text-xl leading-none">📄</button>
            <span :class="statusMap[detail.status]?.[1]" class="text-xs rounded-full px-2 py-1">{{ statusMap[detail.status]?.[0] }}</span>
            <button @click="detail = null" class="text-slate-400 hover:text-slate-600 text-xl leading-none">✕</button>
          </div>
        </div>
        <div class="border rounded-lg overflow-x-auto mb-3">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left text-xs"><tr>
              <th class="px-3 py-2">Karyawan</th><th class="px-3 py-2 text-right">Pokok</th><th class="px-3 py-2 text-right">Tunjangan</th>
              <th class="px-3 py-2 text-right">Kasbon</th><th class="px-3 py-2 text-right">Pot. lain</th><th class="px-3 py-2 text-right">Net</th><th class="px-3 py-2"></th>
            </tr></thead>
            <tbody>
              <tr v-for="it in detail.items" :key="it.id" class="border-t">
                <td class="px-3 py-2 text-slate-700">{{ it.employee_name }}<div class="text-xs text-slate-400">{{ it.position }}</div></td>
                <td class="px-3 py-2 text-right">{{ rupiah(it.base_salary) }}</td>
                <td class="px-3 py-2 text-right">
                  <input v-if="editable" v-model.number="it.allowance" @change="saveItem(it)" type="number" class="w-24 rounded border border-slate-300 px-1 py-0.5 text-right text-xs outline-none" />
                  <span v-else>{{ rupiah(it.allowance) }}</span>
                </td>
                <td class="px-3 py-2 text-right text-amber-600">-{{ rupiah(it.kasbon_deduction) }}</td>
                <td class="px-3 py-2 text-right">
                  <input v-if="editable" v-model.number="it.other_deduction" @change="saveItem(it)" type="number" class="w-20 rounded border border-slate-300 px-1 py-0.5 text-right text-xs outline-none" />
                  <span v-else>-{{ rupiah(it.other_deduction) }}</span>
                </td>
                <td class="px-3 py-2 text-right font-semibold">{{ rupiah(it.net_salary) }}</td>
                <td class="px-3 py-2 text-right"><button @click="slip(it)" class="text-brand-600 text-xs hover:underline">Slip</button></td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="border-t bg-slate-50 font-semibold"><td class="px-3 py-2" colspan="5">Total Gaji Bersih</td><td class="px-3 py-2 text-right">{{ rupiah(detail.total_net) }}</td><td></td></tr>
              <tr v-if="detail.paid_amount != null && detail.paid_amount !== detail.total_net" class="border-t bg-amber-50 font-semibold text-amber-700"><td class="px-3 py-2" colspan="5">Nominal Ditransfer (Aktual)</td><td class="px-3 py-2 text-right">{{ rupiah(detail.paid_amount) }}</td><td></td></tr>
            </tfoot>
          </table>
        </div>
        <p v-if="detail.rejection_reason" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">Ditolak: {{ detail.rejection_reason }}</p>

        <div class="mb-3">
          <div class="flex items-center justify-between mb-1">
            <p class="text-xs font-medium text-slate-500">Data / Bukti Transfer</p>
            <input ref="uploadInput" type="file" accept="image/*,.pdf" class="hidden" @change="onUpload" />
            <button @click="triggerUpload" :disabled="uploading" class="text-xs text-brand-600 hover:underline disabled:opacity-50">{{ uploading ? 'Mengunggah…' : '+ Upload data' }}</button>
          </div>
          <div v-if="!detail.attachments.length" class="text-sm text-slate-400">Tidak ada lampiran.</div>
          <div v-else class="flex flex-wrap gap-2"><button v-for="a in detail.attachments" :key="a.id" @click="viewAtt(a)" class="text-xs bg-slate-100 hover:bg-slate-200 text-slate-600 rounded px-2 py-1">📎 {{ a.filename }}</button></div>
        </div>

        <div class="flex gap-2 pt-2 border-t">
          <button v-if="detail.status === 'draft'" @click="act('submit')" :disabled="busy" class="flex-1 py-2.5 rounded-lg bg-brand-600 text-white font-medium disabled:opacity-50">Ajukan ke HO</button>
          <template v-else-if="detail.status === 'submitted' && isApprover">
            <button @click="act('approve')" :disabled="busy" class="flex-1 py-2.5 rounded-lg bg-emerald-600 text-white font-medium disabled:opacity-50">Setujui</button>
            <button @click="doReject" :disabled="busy" class="flex-1 py-2.5 rounded-lg bg-red-600 text-white font-medium disabled:opacity-50">Tolak</button>
          </template>
          <div v-else-if="detail.status === 'approved' && isApprover" class="w-full">
            <label class="block text-xs text-slate-500 mb-1">Sumber dana</label>
            <select v-model="sourceAccount" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500 mb-2">
              <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }} ({{ rupiah(a.balance) }})</option>
            </select>
            <label class="block text-xs text-slate-500 mb-1">Jumlah transfer</label>
            <input v-model.number="transferAmount" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-right outline-none focus:border-brand-500 mb-1" />
            <p class="text-xs text-slate-400 mb-2">Default = Total Gaji Bersih ({{ rupiah(detail.total_net) }}). Bisa diubah manual (mis. karena pembulatan) — tetap dianggap Lunas berapa pun nominalnya, dan tetap memotong rekening di Kas &amp; Bank sebesar ini.</p>
            <button @click="act('pay', { source_account_id: sourceAccount, amount: transferAmount })" :disabled="busy" class="w-full py-2.5 rounded-lg bg-brand-600 text-white font-medium disabled:opacity-50">Bayar (Transfer) — potong kasbon</button>
          </div>
          <p v-else class="text-sm text-slate-400 py-2 text-center w-full">Status: {{ statusMap[detail.status]?.[0] }}<span v-if="detail.status === 'submitted'"> — menunggu Head Office</span></p>
        </div>
        <div v-if="detail.status !== 'draft' && canRevert" class="flex gap-2 pt-2">
          <button @click="revertRun" :disabled="busy" class="flex-1 py-2 rounded-lg bg-amber-50 hover:bg-amber-100 text-amber-700 font-medium disabled:opacity-50">↩️ Batal Pengajuan (kembali ke Draft)</button>
        </div>
        <div v-if="canDeleteRun(detail)" class="flex gap-2 pt-2">
          <button @click="removeRun(detail)" class="flex-1 py-2 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 font-medium">Hapus Payroll</button>
        </div>
      </div>
    </div>

  </div>
</template>
