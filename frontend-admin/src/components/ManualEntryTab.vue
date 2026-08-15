<script setup>
// Tab entri manual berkategori (Lembur / Reward / Pekerjaan Tambahan) — konsep
// sama: buat batch → baris → Detail utk isi nilai → Ajukan ke HO → Setujui/Tolak.
// Semua kategori pakai endpoint /payroll/overtime/* dgn param `category`.
import { ref, computed, onMounted, watch } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'

const props = defineProps({
  category: { type: String, required: true },
  label: { type: String, required: true },
  venueId: { type: [String, Number], default: '' },
  period: { type: String, required: true },
  isManager: Boolean,
  isApprover: Boolean,
  canEdit: Boolean,
  venues: { type: Array, default: () => [] },
})

const auth = useAuthStore()
const toast = useToastStore()
function flash(m) { toast.show(m) }
const MONTHS = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
const statusMap = { draft: ['Draft', 'bg-slate-100 text-slate-600'], submitted: ['Menunggu', 'bg-amber-100 text-amber-700'], approved: ['Disetujui', 'bg-blue-100 text-blue-700'], rejected: ['Ditolak', 'bg-red-100 text-red-600'] }
function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function ym() { const [y, m] = props.period.split('-'); return { period_year: +y, period_month: +m } }
function myVenue() { return props.isManager ? auth.user?.venue_id : props.venueId }
const cat = () => props.category

// --- daftar batch + ringkasan ---
const runsList = ref([])
const runsLoading = ref(false)
const busyCreate = ref(false)
const summary = ref({ draft: { count: 0, total: 0 }, submitted: { count: 0, total: 0 }, approved: { count: 0, total: 0 }, rejected: { count: 0, total: 0 } })
async function loadSummary() {
  try { const { data } = await client.get('/payroll/overtime/summary', { params: { category: cat() } }); summary.value = data.summary } catch (_) { /* abaikan */ }
}
async function loadRuns() {
  runsLoading.value = true
  const params = { category: cat() }
  if (!props.isManager && props.venueId) params.venue_id = props.venueId
  try { const { data } = await client.get('/payroll/overtime/runs', { params }); runsList.value = data.runs }
  catch (e) { runsList.value = [] } finally { runsLoading.value = false }
}
async function createRun() {
  const vid = myVenue()
  if (!vid) { alert('Pilih venue dulu (bukan "Semua venue").'); return }
  busyCreate.value = true
  const { period_year, period_month } = ym()
  try {
    const { data } = await client.post('/payroll/overtime/runs', { venue_id: vid, period_year, period_month, category: cat() })
    await loadRuns(); loadSummary(); flash(`${props.label} dibuat`)
    if (data.run) openDetail(data.run)
  } catch (e) { alert(e?.response?.data?.message || 'Gagal membuat.') } finally { busyCreate.value = false }
}
const canDeleteRun = (r) => ['draft', 'rejected'].includes(r.status)
async function deleteRun(run, ev) {
  ev?.stopPropagation()
  if (!window.confirm(`Hapus ${props.label} ${MONTHS[run.period_month]} ${run.period_year}?`)) return
  try {
    await client.delete(`/payroll/overtime/runs/${run.id}`)
    if (detail.value?.id === run.id) detail.value = null
    await loadRuns(); loadSummary(); flash('Dihapus')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal menghapus.') }
}

// --- detail modal ---
const detail = ref(null)
const rows = ref([])
const run = ref({ status: 'draft' })
const loading = ref(false)
const saving = ref(false)
const busy = ref(false)
const editable = computed(() => ['draft', 'rejected'].includes(run.value?.status || 'draft') && props.canEdit)
const total = computed(() => rows.value.reduce((s, r) => s + (Number(r.amount) || 0), 0))
async function openDetail(r) {
  detail.value = { ...r }
  rows.value = []; run.value = { status: r.status }
  loading.value = true
  try {
    const { data } = await client.get('/payroll/overtime', { params: { venue_id: r.venue_id, year: r.period_year, month: r.period_month, category: cat() } })
    rows.value = data.items; run.value = data.run || { status: 'draft' }
  } catch (e) { /* abaikan */ } finally { loading.value = false }
}
async function saveAll() {
  const d = detail.value
  if (!d || !rows.value.length) return
  saving.value = true
  try {
    const { data } = await client.put('/payroll/overtime/bulk', {
      venue_id: d.venue_id, period_year: d.period_year, period_month: d.period_month, category: cat(),
      items: rows.value.map((r) => ({ employee_id: r.employee_id, amount: Number(r.amount) || 0, note: r.note || null })),
    })
    if (data.run) run.value = data.run
    loadRuns(); loadSummary(); flash(`Tersimpan (${data.saved} karyawan)`)
  } catch (e) { alert(e?.response?.data?.message || 'Gagal menyimpan.') } finally { saving.value = false }
}
async function action(act, extra = {}) {
  const d = detail.value
  if (!d) return
  busy.value = true
  try {
    const { data } = await client.post(`/payroll/overtime/${act}`, { venue_id: d.venue_id, period_year: d.period_year, period_month: d.period_month, category: cat(), ...extra })
    if (data.run) run.value = data.run
    await loadRuns(); loadSummary(); flash('Berhasil')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
function submit() { if (!window.confirm(`Ajukan ${props.label} ini ke HO? Setelah diajukan tidak bisa diubah sampai ditinjau.`)) return; action('submit') }
function reject() { const reason = prompt('Alasan penolakan:'); if (reason !== null) action('reject', { reason }) }

onMounted(() => { loadRuns(); loadSummary() })
watch(() => props.venueId, () => loadRuns())
</script>

<template>
  <div>
    <!-- Stiker ringkasan per status -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
      <div class="bg-white rounded-xl shadow-sm border p-4">
        <p class="text-xs text-slate-400 mb-1">Draft ({{ summary.draft.count }})</p>
        <p class="text-lg font-bold text-slate-600">{{ rupiah(summary.draft.total) }}</p>
      </div>
      <div class="bg-white rounded-xl shadow-sm border p-4">
        <p class="text-xs text-slate-400 mb-1">Menunggu ({{ summary.submitted.count }})</p>
        <p class="text-lg font-bold text-amber-600">{{ rupiah(summary.submitted.total) }}</p>
      </div>
      <div class="bg-white rounded-xl shadow-sm border p-4">
        <p class="text-xs text-slate-400 mb-1">Disetujui ({{ summary.approved.count }})</p>
        <p class="text-lg font-bold text-emerald-600">{{ rupiah(summary.approved.total) }}</p>
      </div>
      <div class="bg-white rounded-xl shadow-sm border p-4">
        <p class="text-xs text-slate-400 mb-1">Ditolak ({{ summary.rejected.count }})</p>
        <p class="text-lg font-bold text-red-600">{{ rupiah(summary.rejected.total) }}</p>
      </div>
    </div>

    <div class="flex items-center justify-between mb-3">
      <p v-if="!isManager && !venueId" class="text-xs text-amber-600">Pilih venue tertentu (bukan "Semua venue") untuk membuat {{ label.toLowerCase() }} baru.</p>
      <span v-else />
      <button v-if="canEdit" @click="createRun" :disabled="busyCreate || (!isManager && !venueId)"
        class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">
        Buat {{ label }}
      </button>
    </div>

    <!-- Daftar batch -->
    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th v-if="!isManager" class="px-4 py-3 font-medium">Venue</th>
            <th class="px-4 py-3 font-medium">Periode</th>
            <th class="px-4 py-3 font-medium text-center">Karyawan</th>
            <th class="px-4 py-3 font-medium text-right">Total</th>
            <th class="px-4 py-3 font-medium text-center">Status</th>
            <th class="px-4 py-3"></th>
          </tr></thead>
          <tbody>
            <tr v-if="runsLoading"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!runsList.length"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Belum ada {{ label.toLowerCase() }}. Klik "Buat {{ label }}".</td></tr>
            <tr v-for="r in runsList" :key="r.id" @click="openDetail(r)" class="border-t hover:bg-slate-50 cursor-pointer">
              <td v-if="!isManager" class="px-4 py-3 text-slate-600">{{ venues.find(v=>v.id===r.venue_id)?.code || '—' }}</td>
              <td class="px-4 py-3 text-slate-600">{{ MONTHS[r.period_month] }} {{ r.period_year }}</td>
              <td class="px-4 py-3 text-center">{{ r.employee_count }}</td>
              <td class="px-4 py-3 text-right font-medium">{{ rupiah(r.total_amount) }}</td>
              <td class="px-4 py-3 text-center"><span :class="statusMap[r.status]?.[1] || 'bg-slate-100 text-slate-600'" class="text-xs rounded-full px-2 py-0.5">{{ statusMap[r.status]?.[0] || 'Draft' }}</span></td>
              <td class="px-4 py-3 text-right text-sm whitespace-nowrap">
                <span class="text-brand-600">Detail</span>
                <button v-if="canDeleteRun(r) && canEdit" @click="deleteRun(r, $event)" class="text-red-500 hover:underline ml-3">Hapus</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Detail modal -->
    <div v-if="detail" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="detail = null">
      <div class="bg-white w-full max-w-3xl rounded-2xl max-h-[92vh] overflow-auto">
        <div class="flex justify-between items-start p-5 pb-3">
          <div class="flex items-center gap-2">
            <div>
              <h3 class="text-lg font-bold text-slate-800">{{ label }} {{ MONTHS[detail.period_month] }} {{ detail.period_year }}</h3>
              <p class="text-sm text-slate-500">{{ venues.find(v=>v.id===detail.venue_id)?.name || '' }}</p>
            </div>
            <span :class="statusMap[run.status]?.[1] || 'bg-slate-100 text-slate-600'" class="text-xs rounded-full px-2 py-0.5">{{ statusMap[run.status]?.[0] || 'Draft' }}</span>
          </div>
          <button @click="detail = null" class="text-slate-400 hover:text-slate-600 text-xl leading-none">✕</button>
        </div>

        <div class="flex items-center justify-between flex-wrap gap-3 px-5 py-2 bg-slate-50 border-y">
          <div class="flex items-center gap-3">
            <p class="text-sm font-semibold text-slate-700">Total: {{ rupiah(total) }}</p>
            <button v-if="['draft','rejected'].includes(run.status) && canEdit" @click="deleteRun(detail)"
              class="text-red-500 hover:text-red-600 text-sm hover:underline">Hapus</button>
          </div>
          <div class="flex items-center gap-2">
            <template v-if="editable">
              <button @click="saveAll" :disabled="saving || !rows.length"
                class="bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">
                {{ saving ? 'Menyimpan…' : 'Simpan Semua' }}
              </button>
              <button @click="submit" :disabled="busy || !total" :title="!total ? 'Isi & simpan nilai dulu' : ''"
                class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">Ajukan ke HO</button>
            </template>
            <template v-else-if="run.status === 'submitted' && isApprover">
              <button @click="action('approve')" :disabled="busy" class="bg-emerald-600 hover:bg-emerald-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">Setujui</button>
              <button @click="reject" :disabled="busy" class="bg-red-600 hover:bg-red-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">Tolak</button>
            </template>
            <span v-else-if="run.status === 'submitted'" class="text-sm text-amber-600">Menunggu persetujuan HO</span>
          </div>
        </div>

        <p v-if="run.status === 'rejected' && run.rejection_reason" class="text-sm text-red-600 bg-red-50 px-5 py-2">
          Ditolak HO: {{ run.rejection_reason }}
        </p>

        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-5 py-3 font-medium">Karyawan</th>
              <th class="px-4 py-3 font-medium">Jabatan</th>
              <th class="px-4 py-3 font-medium text-right">Nilai (Rp)</th>
              <th class="px-4 py-3 font-medium">Catatan</th>
            </tr></thead>
            <tbody>
              <tr v-if="loading"><td colspan="4" class="px-5 py-8 text-center text-slate-400">Memuat…</td></tr>
              <tr v-else-if="!rows.length"><td colspan="4" class="px-5 py-8 text-center text-slate-400">Tidak ada karyawan aktif di venue ini.</td></tr>
              <tr v-for="row in rows" :key="row.employee_id" class="border-t">
                <td class="px-5 py-2.5 text-slate-700">{{ row.employee_name }}</td>
                <td class="px-4 py-2.5 text-slate-500 text-xs">{{ row.position || '—' }}</td>
                <td class="px-4 py-2 text-right">
                  <input v-model.number="row.amount" type="number" min="0" step="1000" :disabled="!editable"
                    class="w-32 text-right rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-500" />
                </td>
                <td class="px-4 py-2">
                  <input v-model="row.note" type="text" placeholder="opsional" :disabled="!editable"
                    class="w-full min-w-[8rem] rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-500" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="p-4" />
      </div>
    </div>
  </div>
</template>
