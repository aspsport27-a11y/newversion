<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isManager = computed(() => auth.user?.role === 'manager_unit')
const isApprover = computed(() => ['admin', 'head_office'].includes(auth.user?.role))

const venues = ref([])
const venueId = ref('')
const now = new Date()
const period = ref(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
const runs = ref([])
const loading = ref(false)
const detail = ref(null)
const busy = ref(false)
const toast = ref('')

function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2500) }
function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function ym() { const [y, m] = period.value.split('-'); return { year: +y, month: +m } }
const MONTHS = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
const statusMap = { draft: ['Draft', 'bg-slate-100 text-slate-600'], submitted: ['Menunggu', 'bg-amber-100 text-amber-700'], approved: ['Disetujui', 'bg-blue-100 text-blue-700'], paid: ['Dibayar', 'bg-emerald-100 text-emerald-700'], rejected: ['Ditolak', 'bg-red-100 text-red-600'] }
const editable = computed(() => detail.value && ['draft', 'submitted'].includes(detail.value.status))

async function loadVenues() {
  const { data } = await client.get('/admin/venues')
  venues.value = data.venues
  if (!isManager.value && venues.value.length && !venueId.value) venueId.value = venues.value[0].id
}
async function loadRuns() {
  loading.value = true
  const params = {}
  if (!isManager.value && venueId.value) params.venue_id = venueId.value
  try { const { data } = await client.get('/payroll/runs', { params }); runs.value = data.runs }
  finally { loading.value = false }
}
onMounted(async () => { await loadVenues(); await loadRuns() })
watch([venueId], loadRuns)

async function generate() {
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
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select>
        <input v-model="period" type="month" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
        <button @click="generate" :disabled="busy" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">Generate Gaji</button>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-3 font-medium">Kode</th><th class="px-4 py-3 font-medium">Periode</th>
            <th class="px-4 py-3 font-medium text-center">Karyawan</th><th class="px-4 py-3 font-medium text-right">Total Net</th>
            <th class="px-4 py-3 font-medium text-center">Status</th><th class="px-4 py-3"></th>
          </tr></thead>
          <tbody>
            <tr v-if="loading"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!runs.length"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Belum ada payroll. Klik "Generate Gaji".</td></tr>
            <tr v-for="r in runs" :key="r.id" @click="openDetail(r)" class="border-t hover:bg-slate-50 cursor-pointer">
              <td class="px-4 py-3 font-mono text-xs text-slate-500">{{ r.code }}</td>
              <td class="px-4 py-3 text-slate-600">{{ MONTHS[r.period_month] }} {{ r.period_year }}</td>
              <td class="px-4 py-3 text-center">{{ r.employee_count }}</td>
              <td class="px-4 py-3 text-right font-medium">{{ rupiah(r.total_net) }}</td>
              <td class="px-4 py-3 text-center"><span :class="statusMap[r.status]?.[1]" class="text-xs rounded-full px-2 py-0.5">{{ statusMap[r.status]?.[0] }}</span></td>
              <td class="px-4 py-3 text-right text-brand-600 text-sm">Detail</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Detail -->
    <div v-if="detail" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="detail = null">
      <div class="bg-white w-full max-w-3xl rounded-2xl p-5 max-h-[92vh] overflow-auto">
        <div class="flex justify-between items-start mb-3">
          <div><h3 class="text-lg font-bold text-slate-800">{{ detail.code }}</h3><p class="text-sm text-slate-500">{{ MONTHS[detail.period_month] }} {{ detail.period_year }}</p></div>
          <span :class="statusMap[detail.status]?.[1]" class="text-xs rounded-full px-2 py-1">{{ statusMap[detail.status]?.[0] }}</span>
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
            <tfoot><tr class="border-t bg-slate-50 font-semibold"><td class="px-3 py-2" colspan="5">Total Gaji Bersih</td><td class="px-3 py-2 text-right">{{ rupiah(detail.total_net) }}</td><td></td></tr></tfoot>
          </table>
        </div>
        <p v-if="detail.rejection_reason" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">Ditolak: {{ detail.rejection_reason }}</p>

        <div class="flex gap-2 pt-2 border-t">
          <button v-if="detail.status === 'draft'" @click="act('submit')" :disabled="busy" class="flex-1 py-2.5 rounded-lg bg-brand-600 text-white font-medium disabled:opacity-50">Ajukan ke HO</button>
          <template v-else-if="detail.status === 'submitted' && isApprover">
            <button @click="act('approve')" :disabled="busy" class="flex-1 py-2.5 rounded-lg bg-emerald-600 text-white font-medium disabled:opacity-50">Setujui</button>
            <button @click="doReject" :disabled="busy" class="flex-1 py-2.5 rounded-lg bg-red-600 text-white font-medium disabled:opacity-50">Tolak</button>
          </template>
          <button v-else-if="detail.status === 'approved' && isApprover" @click="act('pay')" :disabled="busy" class="w-full py-2.5 rounded-lg bg-brand-600 text-white font-medium disabled:opacity-50">Bayar (Transfer) — potong kasbon</button>
          <p v-else class="text-sm text-slate-400 py-2 text-center w-full">Status: {{ statusMap[detail.status]?.[0] }}<span v-if="detail.status === 'submitted'"> — menunggu Head Office</span></p>
        </div>
      </div>
    </div>

    <div v-if="toast" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
