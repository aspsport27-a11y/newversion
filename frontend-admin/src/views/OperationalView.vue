<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isManager = computed(() => auth.user?.role === 'manager_unit')
const isAdminUnit = computed(() => auth.user?.role === 'admin_unit')
const isApprover = computed(() => ['admin', 'head_office'].includes(auth.user?.role))

const tab = ref('requests')
const venues = ref([])
const venueId = ref('')
const categories = ref([])
const now = new Date()
const period = ref(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
const toast = ref('')

function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2500) }
function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function ym() { const [y, m] = period.value.split('-'); return { year: +y, month: +m } }
const statusMap = { submitted: ['Menunggu', 'bg-amber-100 text-amber-700'], approved: ['Disetujui', 'bg-blue-100 text-blue-700'], rejected: ['Ditolak', 'bg-red-100 text-red-600'], disbursed: ['Dicairkan', 'bg-emerald-100 text-emerald-700'] }

const accounts = ref([])
const sourceAccount = ref('')
async function loadBase() {
  const [v, c] = await Promise.all([client.get('/venues'), client.get('/ops/categories')])
  venues.value = v.data.venues
  // admin_unit hanya boleh ajukan utk venue di areanya
  if (isAdminUnit.value) {
    venues.value = venues.value.filter((x) => x.area_id === auth.user?.area_id)
  }
  categories.value = c.data.categories
  // default: "Semua venue" (venueId tetap '') agar semua pengajuan tampil
  if (isApprover.value) {
    try {
      const { data } = await client.get('/treasury/accounts')
      accounts.value = data.accounts
      sourceAccount.value = data.accounts.find((a) => a.type === 'holding')?.id || data.accounts[0]?.id || ''
    } catch (_) { /* treasury belum disetup */ }
  }
}

// ---------- Pengajuan ----------
const requests = ref([])
const statusFilter = ref('')
const loadingReq = ref(false)
async function loadRequests() {
  loadingReq.value = true
  const params = {}
  if (!isManager.value && venueId.value) params.venue_id = venueId.value
  if (statusFilter.value) params.status = statusFilter.value
  try { const { data } = await client.get('/ops/requests', { params }); requests.value = data.requests }
  finally { loadingReq.value = false }
}

// create
const showCreate = ref(false)
const cForm = ref({ description: '', items: [] })
const cFiles = ref([])
const cErr = ref('')
const saving = ref(false)
const cTotal = computed(() => cForm.value.items.reduce((s, i) => s + (Number(i.amount) || 0), 0))
function openCreate() {
  cForm.value = { venue_id: venueId.value || venues.value[0]?.id, description: '', items: [{ category_id: categories.value[0]?.id, amount: null, note: '' }] }
  cFiles.value = []; cErr.value = ''; showCreate.value = true
}
function addRow() { cForm.value.items.push({ category_id: categories.value[0]?.id, amount: null, note: '' }) }
function rmRow(i) { cForm.value.items.splice(i, 1) }
function onFiles(e) { cFiles.value = Array.from(e.target.files) }
async function submitCreate() {
  saving.value = true; cErr.value = ''
  try {
    const payload = { ...ym(), description: cForm.value.description, items: cForm.value.items.filter((i) => i.category_id && i.amount > 0) }
    if (!isManager.value) payload.venue_id = cForm.value.venue_id
    const { data } = await client.post('/ops/requests', payload)
    for (const f of cFiles.value) {
      const fd = new FormData(); fd.append('file', f)
      await client.post(`/ops/requests/${data.request.id}/attachment`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    }
    showCreate.value = false; await loadRequests(); flash('Pengajuan terkirim')
  } catch (e) { cErr.value = e?.response?.data?.message || 'Gagal.' } finally { saving.value = false }
}

// detail
const detail = ref(null)
const busy = ref(false)
async function openDetail(r) {
  const { data } = await client.get(`/ops/requests/${r.id}`); detail.value = data.request
}
async function act(action, extra = {}) {
  busy.value = true
  try {
    await client.post(`/ops/requests/${detail.value.id}/${action}`, extra)
    const { data } = await client.get(`/ops/requests/${detail.value.id}`); detail.value = data.request
    await loadRequests(); flash('Berhasil')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
function doReject() { const reason = prompt('Alasan penolakan:'); if (reason !== null) act('reject', { reason }) }
async function viewAttachment(a) {
  const res = await client.get(`/ops/attachments/${a.id}`, { responseType: 'blob' })
  window.open(URL.createObjectURL(res.data), '_blank')
}
async function revertRequest() {
  const warn = detail.value.status === 'disbursed'
    ? 'Ini akan membalikkan pencairan dana (uang masuk lagi ke Kas & Bank). Lanjutkan?'
    : 'Kembalikan status pengajuan ke Menunggu?'
  if (!window.confirm(warn)) return
  busy.value = true
  try {
    await client.post(`/ops/requests/${detail.value.id}/revert`)
    const { data } = await client.get(`/ops/requests/${detail.value.id}`); detail.value = data.request
    await loadRequests(); flash('Pengajuan dibatalkan — kembali ke Menunggu')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal membatalkan.') } finally { busy.value = false }
}
const canDeleteRequest = (r) => ['submitted', 'approved', 'rejected'].includes(r.status)
async function removeRequest(r, ev) {
  ev?.stopPropagation()
  if (!window.confirm(`Hapus pengajuan ${r.code}?`)) return
  try {
    await client.delete(`/ops/requests/${r.id}`)
    if (detail.value?.id === r.id) detail.value = null
    await loadRequests(); flash('Pengajuan dihapus')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal menghapus.') }
}

// ---------- Budget ----------
const budgetRows = ref([])
const budgetTotals = ref({ budget: 0, used: 0 })
const savingBudget = ref(false)
async function loadBudget() {
  const { year, month } = ym()
  const params = { year, month }
  if (!isManager.value && venueId.value) params.venue_id = venueId.value
  else if (isManager.value) { /* backend forces manager venue */ }
  if (!params.venue_id && !isManager.value) return
  const { data } = await client.get('/ops/budgets', { params })
  budgetRows.value = data.rows
  budgetTotals.value = { budget: data.total_budget, used: data.total_used }
}
async function saveBudget() {
  savingBudget.value = true
  try {
    const { year, month } = ym()
    await client.post('/ops/budgets', { venue_id: venueId.value, year, month, items: budgetRows.value.map((r) => ({ category_id: r.category_id, amount: Number(r.budget) || 0 })) })
    await loadBudget(); flash('Budget disimpan')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { savingBudget.value = false }
}

// --- Kelola Kategori Beban (admin/HO) ---
const catsAll = ref([])
const newCatName = ref('')
const savingCat = ref(false)
async function loadCats() {
  const { data } = await client.get('/ops/categories', { params: { all: 1 } })
  catsAll.value = data.categories
}
async function addCat() {
  if (!newCatName.value.trim()) return
  savingCat.value = true
  try {
    await client.post('/ops/categories', { name: newCatName.value.trim() })
    newCatName.value = ''
    await loadCats(); await loadBase(); flash('Kategori ditambah')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { savingCat.value = false }
}
async function renameCat(c) {
  const nm = prompt('Nama kategori:', c.name)
  if (!nm || nm.trim() === c.name) return
  try { await client.put(`/ops/categories/${c.id}`, { name: nm.trim() }); await loadCats(); await loadBase(); flash('Disimpan') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal.') }
}
async function toggleCat(c) {
  try { await client.put(`/ops/categories/${c.id}`, { is_active: !c.is_active }); await loadCats(); await loadBase() }
  catch (e) { alert('Gagal.') }
}

function reloadTab() {
  if (tab.value === 'requests') loadRequests()
  else if (tab.value === 'budget') loadBudget()
  else if (tab.value === 'categories') loadCats()
}
onMounted(async () => { await loadBase(); await loadRequests() })
watch([venueId, period], reloadTab)
watch(tab, reloadTab)
watch(statusFilter, loadRequests)
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-5">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">Operasional &amp; Budget</h1>
        <p class="text-slate-500 mt-1">Pengajuan dana, approval, pencairan, dan plafon budget.</p>
      </div>
      <div class="flex gap-2 items-center">
        <select v-if="!isManager" v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua venue</option>
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select>
        <input v-model="period" type="month" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 mb-4 border-b">
      <button @click="tab = 'requests'" :class="tab === 'requests' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Pengajuan</button>
      <button @click="tab = 'budget'" :class="tab === 'budget' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Budget</button>
      <button v-if="isApprover" @click="tab = 'categories'" :class="tab === 'categories' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Kategori</button>
    </div>

    <!-- Tab Kategori Beban -->
    <div v-if="tab === 'categories'">
      <p class="text-slate-500 text-sm mb-3">Kategori rincian yang muncul saat mengajukan dana. Nonaktifkan untuk menyembunyikan dari form (tidak menghapus riwayat).</p>
      <div class="bg-white rounded-xl shadow-sm border p-4 mb-4 flex gap-2 max-w-lg">
        <input v-model="newCatName" placeholder="Nama kategori baru (mis. Ops Kebersihan)" @keyup.enter="addCat" class="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
        <button @click="addCat" :disabled="savingCat" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">+ Tambah</button>
      </div>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden max-w-lg">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-2 font-medium">Kategori</th><th class="px-4 py-2 font-medium text-center">Status</th><th class="px-4 py-2"></th>
          </tr></thead>
          <tbody>
            <tr v-if="!catsAll.length"><td colspan="3" class="px-4 py-6 text-center text-slate-400">Belum ada kategori.</td></tr>
            <tr v-for="c in catsAll" :key="c.id" class="border-t">
              <td class="px-4 py-2 text-slate-700" :class="{ 'text-slate-400 line-through': !c.is_active }">{{ c.name }}</td>
              <td class="px-4 py-2 text-center">
                <span class="text-xs px-2 py-0.5 rounded-full" :class="c.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'">{{ c.is_active ? 'Aktif' : 'Nonaktif' }}</span>
              </td>
              <td class="px-4 py-2 text-right whitespace-nowrap">
                <button @click="renameCat(c)" class="text-brand-600 text-xs hover:underline mr-3">Ubah</button>
                <button @click="toggleCat(c)" class="text-xs hover:underline" :class="c.is_active ? 'text-red-500' : 'text-emerald-600'">{{ c.is_active ? 'Nonaktifkan' : 'Aktifkan' }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ============ PENGAJUAN ============ -->
    <div v-if="tab === 'requests'">
      <div class="flex justify-between items-center mb-3 flex-wrap gap-2">
        <select v-model="statusFilter" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua status</option>
          <option value="submitted">Menunggu</option><option value="approved">Disetujui</option>
          <option value="disbursed">Dicairkan</option><option value="rejected">Ditolak</option>
        </select>
        <button @click="openCreate" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Ajukan Dana</button>
      </div>

      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-4 py-3 font-medium">Kode</th>
              <th v-if="!isManager" class="px-4 py-3 font-medium">Venue</th>
              <th class="px-4 py-3 font-medium">Periode</th>
              <th class="px-4 py-3 font-medium">Deskripsi</th><th class="px-4 py-3 font-medium text-right">Total</th>
              <th class="px-4 py-3 font-medium text-center">Status</th><th class="px-4 py-3"></th>
            </tr></thead>
            <tbody>
              <tr v-if="loadingReq"><td colspan="7" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
              <tr v-else-if="!requests.length"><td colspan="7" class="px-4 py-8 text-center text-slate-400">Belum ada pengajuan.</td></tr>
              <tr v-for="r in requests" :key="r.id" @click="openDetail(r)" class="border-t hover:bg-slate-50 cursor-pointer">
                <td class="px-4 py-3 font-mono text-xs text-slate-500">{{ r.code }}</td>
                <td v-if="!isManager" class="px-4 py-3 text-slate-600">{{ venues.find(v=>v.id===r.venue_id)?.code || '—' }}</td>
                <td class="px-4 py-3 text-slate-600">{{ r.period_month }}/{{ r.period_year }}</td>
                <td class="px-4 py-3 text-slate-600 max-w-xs truncate">{{ r.description || '—' }}</td>
                <td class="px-4 py-3 text-right font-medium">{{ rupiah(r.total_amount) }}</td>
                <td class="px-4 py-3 text-center"><span :class="statusMap[r.status]?.[1]" class="text-xs rounded-full px-2 py-0.5">{{ statusMap[r.status]?.[0] }}</span></td>
                <td class="px-4 py-3 text-right text-sm whitespace-nowrap">
                  <span class="text-brand-600">Detail</span>
                  <button v-if="canDeleteRequest(r)" @click="removeRequest(r, $event)" class="text-red-500 hover:underline ml-3">Hapus</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ============ BUDGET ============ -->
    <div v-else-if="tab === 'budget'">
      <div v-if="!isManager && !venueId" class="bg-amber-50 text-amber-700 text-sm rounded-lg px-4 py-3 mb-3">Pilih satu venue dulu (bukan "Semua venue") untuk mengatur budget.</div>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="flex justify-between items-center px-4 py-3 border-b">
          <span class="text-sm text-slate-500">Plafon budget per kategori — {{ period }}</span>
          <button v-if="isApprover" @click="saveBudget" :disabled="savingBudget" class="bg-brand-600 hover:bg-brand-700 text-white text-xs rounded-lg px-4 py-1.5 font-medium disabled:opacity-50">Simpan Budget</button>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-4 py-3 font-medium">Kategori</th><th class="px-4 py-3 font-medium text-right">Plafon</th>
              <th class="px-4 py-3 font-medium text-right">Terpakai</th><th class="px-4 py-3 font-medium text-right">Sisa</th>
            </tr></thead>
            <tbody>
              <tr v-for="r in budgetRows" :key="r.category_id" class="border-t">
                <td class="px-4 py-2.5 text-slate-700">{{ r.category_name }}</td>
                <td class="px-4 py-2.5 text-right">
                  <input v-if="isApprover" v-model.number="r.budget" type="number" class="w-32 rounded border border-slate-300 px-2 py-1 text-right text-sm outline-none focus:border-brand-500" />
                  <span v-else>{{ rupiah(r.budget) }}</span>
                </td>
                <td class="px-4 py-2.5 text-right text-slate-600">{{ rupiah(r.used) }}</td>
                <td class="px-4 py-2.5 text-right font-medium" :class="r.remaining < 0 ? 'text-red-600' : 'text-emerald-600'">{{ rupiah(r.remaining) }}</td>
              </tr>
            </tbody>
            <tfoot><tr class="border-t bg-slate-50 font-semibold">
              <td class="px-4 py-2.5">Total</td>
              <td class="px-4 py-2.5 text-right">{{ rupiah(budgetTotals.budget) }}</td>
              <td class="px-4 py-2.5 text-right">{{ rupiah(budgetTotals.used) }}</td>
              <td class="px-4 py-2.5 text-right">{{ rupiah(budgetTotals.budget - budgetTotals.used) }}</td>
            </tr></tfoot>
          </table>
        </div>
      </div>
    </div>

    <!-- Create modal -->
    <div v-if="showCreate" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-lg rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-center mb-4"><h3 class="text-lg font-bold text-slate-800">Ajukan Dana Operasional</h3><button @click="showCreate = false" class="text-slate-400 text-xl">✕</button></div>
        <p class="text-xs text-slate-400 mb-3">Periode {{ period }}</p>
        <div v-if="!isManager" class="mb-3">
          <label class="block text-xs text-slate-500 mb-1">Venue</label>
          <select v-model="cForm.venue_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
            <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
          </select>
        </div>
        <textarea v-model="cForm.description" placeholder="Deskripsi / keterangan" rows="2" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500 mb-3"></textarea>
        <p class="text-xs font-medium text-slate-500 mb-1">Rincian</p>
        <div v-for="(it, i) in cForm.items" :key="i" class="flex gap-2 mb-2">
          <select v-model="it.category_id" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none w-40">
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
          <input v-model.number="it.amount" type="number" placeholder="Jumlah" class="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm text-right outline-none" />
          <button @click="rmRow(i)" class="text-red-400 px-1">✕</button>
        </div>
        <button @click="addRow" class="text-brand-600 text-sm mb-3">+ baris</button>
        <div class="flex justify-between font-semibold mb-3"><span>Total</span><span class="text-brand-700">{{ rupiah(cTotal) }}</span></div>
        <label class="block text-xs text-slate-500 mb-1">Bukti (foto/PDF, boleh &gt;1)</label>
        <input type="file" multiple accept="image/*,.pdf" @change="onFiles" class="w-full text-sm mb-3" />
        <p v-if="cErr" class="text-sm text-red-600 mb-2">{{ cErr }}</p>
        <button @click="submitCreate" :disabled="saving || !cTotal" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">{{ saving ? 'Mengirim…' : 'Kirim Pengajuan' }}</button>
      </div>
    </div>

    <!-- Detail modal -->
    <div v-if="detail" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="detail = null">
      <div class="bg-white w-full max-w-lg rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-start mb-3">
          <div><h3 class="text-lg font-bold text-slate-800">{{ detail.code }}</h3><p class="text-sm text-slate-500">Periode {{ detail.period_month }}/{{ detail.period_year }}</p></div>
          <div class="flex items-center gap-2">
            <span :class="statusMap[detail.status]?.[1]" class="text-xs rounded-full px-2 py-1">{{ statusMap[detail.status]?.[0] }}</span>
            <button @click="detail = null" class="text-slate-400 hover:text-slate-600 text-xl leading-none">✕</button>
          </div>
        </div>
        <p v-if="detail.description" class="text-sm text-slate-600 mb-3">{{ detail.description }}</p>

        <div class="border rounded-lg overflow-hidden mb-3">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left text-xs"><tr><th class="px-3 py-2">Kategori</th><th class="px-3 py-2 text-right">Jumlah</th><th class="px-3 py-2 text-right">Sisa budget</th></tr></thead>
            <tbody>
              <tr v-for="it in detail.items" :key="it.id" class="border-t">
                <td class="px-3 py-2 text-slate-700">{{ it.category_name }}<div v-if="it.note" class="text-xs text-slate-400">{{ it.note }}</div></td>
                <td class="px-3 py-2 text-right">{{ rupiah(it.amount) }}</td>
                <td class="px-3 py-2 text-right text-xs" :class="it.budget_remaining < 0 ? 'text-red-600' : 'text-slate-400'">{{ it.budget != null ? rupiah(it.budget_remaining) : '—' }}</td>
              </tr>
            </tbody>
            <tfoot><tr class="border-t bg-slate-50 font-semibold"><td class="px-3 py-2">Total</td><td class="px-3 py-2 text-right">{{ rupiah(detail.total_amount) }}</td><td></td></tr></tfoot>
          </table>
        </div>

        <div v-if="detail.rejection_reason" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">Ditolak: {{ detail.rejection_reason }}</div>

        <!-- Lampiran -->
        <div class="mb-3">
          <p class="text-xs font-medium text-slate-500 mb-1">Bukti</p>
          <div v-if="!detail.attachments.length" class="text-sm text-slate-400">Tidak ada lampiran.</div>
          <div v-else class="flex flex-wrap gap-2">
            <button v-for="a in detail.attachments" :key="a.id" @click="viewAttachment(a)" class="text-xs bg-slate-100 hover:bg-slate-200 text-slate-600 rounded px-2 py-1">📎 {{ a.filename }}</button>
          </div>
        </div>

        <!-- Aksi Head Office -->
        <div v-if="isApprover" class="pt-2 border-t space-y-2">
          <div v-if="detail.status === 'submitted'" class="flex gap-2">
            <button @click="act('approve')" :disabled="busy" class="flex-1 py-2.5 rounded-lg bg-emerald-600 text-white font-medium disabled:opacity-50">Setujui</button>
            <button @click="doReject" :disabled="busy" class="flex-1 py-2.5 rounded-lg bg-red-600 text-white font-medium disabled:opacity-50">Tolak</button>
          </div>
          <template v-else-if="detail.status === 'approved'">
            <div>
              <label class="block text-xs text-slate-500 mb-1">Sumber dana</label>
              <select v-model="sourceAccount" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
                <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }} ({{ rupiah(a.balance) }})</option>
              </select>
            </div>
            <button @click="act('disburse', { source_account_id: sourceAccount })" :disabled="busy" class="w-full py-2.5 rounded-lg bg-brand-600 text-white font-medium disabled:opacity-50">Cairkan Dana</button>
          </template>
          <p v-else class="text-sm text-slate-400 py-2">Status: {{ statusMap[detail.status]?.[0] }}</p>
        </div>
        <div v-if="detail.status !== 'submitted' && isApprover" class="flex gap-2 pt-2">
          <button @click="revertRequest" :disabled="busy" class="flex-1 py-2 rounded-lg bg-amber-50 hover:bg-amber-100 text-amber-700 font-medium disabled:opacity-50">↩️ Batal (kembali ke Menunggu)</button>
        </div>
        <div v-if="canDeleteRequest(detail)" class="flex gap-2 pt-2">
          <button @click="removeRequest(detail)" class="flex-1 py-2 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 font-medium">Hapus Pengajuan</button>
        </div>
      </div>
    </div>

    <div v-if="toast" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
