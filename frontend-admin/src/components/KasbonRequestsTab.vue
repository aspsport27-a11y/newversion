<script setup>
// Tab Pengajuan Kasbon (di menu Karyawan). Alur: ajukan (jumlah + tenor bulan →
// cicilan otomatis) → HO Setujui/Tolak. Saat disetujui, backend otomatis catat
// advance + set cicilan di karyawan; payroll lalu memotong otomatis.
import { ref, computed, onMounted, watch } from 'vue'
import client from '../api/client'
import { useToastStore } from '../stores/toast'

const props = defineProps({
  venueId: { type: [String, Number], default: '' },
  isManager: Boolean,
  isApprover: Boolean,
  canManage: Boolean,
  venues: { type: Array, default: () => [] },
})

const toast = useToastStore()
function flash(m) { toast.show(m) }
function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
const statusMap = { submitted: ['Menunggu', 'bg-amber-100 text-amber-700'], approved: ['Disetujui', 'bg-emerald-100 text-emerald-700'], rejected: ['Ditolak', 'bg-red-100 text-red-600'] }

const requests = ref([])
const loading = ref(false)
const busy = ref(false)
async function loadRequests() {
  loading.value = true
  // Kasbon = antrian approval lintas venue: SELALU tampilkan seluruh scope (bukan
  // difilter per venue terpilih), supaya jumlah di lonceng notifikasi = isi tabel.
  // Kolom "Venue" membedakan asalnya. (Notif menghitung semua submitted dalam scope.)
  try { const { data } = await client.get('/admin/kasbon-requests'); requests.value = data.requests }
  catch (e) { requests.value = [] } finally { loading.value = false }
}
const summary = computed(() => {
  const s = { submitted: { count: 0, total: 0 }, approved: { count: 0, total: 0 }, rejected: { count: 0, total: 0 } }
  for (const r of requests.value) { const k = s[r.status] ? r.status : 'submitted'; s[k].count += 1; s[k].total += Number(r.amount) || 0 }
  return s
})

// --- ajukan ---
const showCreate = ref(false)
const employees = ref([])
const form = ref({ employee_id: '', amount: null, months: 1, note: '' })
const saving = ref(false)
const cErr = ref('')
const installmentPreview = computed(() => {
  const a = Number(form.value.amount) || 0, m = Number(form.value.months) || 0
  return a > 0 && m > 0 ? Math.ceil(a / m) : 0
})
async function openCreate() {
  if (!props.isManager && !props.venueId) { alert('Pilih venue tertentu dulu (bukan "Semua venue").'); return }
  cErr.value = ''
  form.value = { employee_id: '', amount: null, months: 1, note: '' }
  showCreate.value = true
  try {
    const params = {}
    if (!props.isManager && props.venueId) params.venue_id = props.venueId
    const { data } = await client.get('/admin/employees', { params })
    employees.value = data.employees.filter((e) => e.status === 'active')
  } catch (e) { employees.value = [] }
}
async function submitCreate() {
  cErr.value = ''
  if (!form.value.employee_id) { cErr.value = 'Pilih karyawan dulu'; return }
  if (!(Number(form.value.amount) > 0)) { cErr.value = 'Jumlah kasbon harus > 0'; return }
  if (!(Number(form.value.months) >= 1)) { cErr.value = 'Jumlah bulan minimal 1'; return }
  saving.value = true
  try {
    await client.post('/admin/kasbon-requests', {
      employee_id: form.value.employee_id, amount: Number(form.value.amount),
      months: Number(form.value.months), note: form.value.note || null,
    })
    showCreate.value = false
    await loadRequests(); flash('Pengajuan kasbon terkirim')
  } catch (e) { cErr.value = e?.response?.data?.message || 'Gagal mengirim.' } finally { saving.value = false }
}

async function act(r, action, extra = {}) {
  busy.value = true
  try {
    await client.post(`/admin/kasbon-requests/${r.id}/${action}`, extra)
    await loadRequests(); flash('Berhasil')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
function approve(r) { if (window.confirm(`Setujui kasbon ${r.employee_name} sebesar ${rupiah(r.amount)}? Saldo & cicilan akan langsung ditulis ke data karyawan.`)) act(r, 'approve') }
function reject(r) { const reason = prompt('Alasan penolakan:'); if (reason !== null) act(r, 'reject', { reason }) }
async function del(r) {
  if (!window.confirm(`Hapus pengajuan kasbon ${r.employee_name}?`)) return
  busy.value = true
  try { await client.delete(`/admin/kasbon-requests/${r.id}`); await loadRequests(); flash('Dihapus') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal menghapus.') } finally { busy.value = false }
}

onMounted(loadRequests)
watch(() => props.venueId, loadRequests)
</script>

<template>
  <div>
    <!-- Stiker ringkasan per status -->
    <div class="grid grid-cols-3 gap-3 mb-4">
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
      <p v-if="!isManager && !venueId" class="text-xs text-amber-600">Pilih venue tertentu untuk mengajukan kasbon.</p>
      <span v-else />
      <button v-if="canManage" @click="openCreate" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Ajukan Kasbon</button>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-3 font-medium">Karyawan</th>
            <th v-if="!isManager" class="px-4 py-3 font-medium">Venue</th>
            <th class="px-4 py-3 font-medium text-right">Jumlah</th>
            <th class="px-4 py-3 font-medium text-right">Cicilan/bln</th>
            <th class="px-4 py-3 font-medium text-center">Tenor</th>
            <th class="px-4 py-3 font-medium text-right">Sisa Kasbon</th>
            <th class="px-4 py-3 font-medium text-center">Status</th>
            <th class="px-4 py-3"></th>
          </tr></thead>
          <tbody>
            <tr v-if="loading"><td colspan="8" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!requests.length"><td colspan="8" class="px-4 py-8 text-center text-slate-400">Belum ada pengajuan kasbon.</td></tr>
            <tr v-for="r in requests" :key="r.id" class="border-t">
              <td class="px-4 py-3 text-slate-700">{{ r.employee_name }}<div v-if="r.note" class="text-xs text-slate-400">{{ r.note }}</div>
                <div v-if="r.status === 'rejected' && r.rejection_reason" class="text-xs text-red-500">Ditolak: {{ r.rejection_reason }}</div>
              </td>
              <td v-if="!isManager" class="px-4 py-3 text-slate-500 text-xs">{{ r.venue_code || '—' }}</td>
              <td class="px-4 py-3 text-right font-medium">{{ rupiah(r.amount) }}</td>
              <td class="px-4 py-3 text-right text-slate-600">{{ rupiah(r.installment) }}</td>
              <td class="px-4 py-3 text-center text-slate-500">{{ r.months }} bln</td>
              <td class="px-4 py-3 text-right" :class="r.debt_balance > 0 ? 'text-amber-600 font-medium' : 'text-emerald-600'">{{ rupiah(r.debt_balance) }}</td>
              <td class="px-4 py-3 text-center"><span :class="statusMap[r.status]?.[1]" class="text-xs rounded-full px-2 py-0.5">{{ statusMap[r.status]?.[0] }}</span></td>
              <td class="px-4 py-3 text-right text-sm whitespace-nowrap">
                <template v-if="r.status === 'submitted' && isApprover">
                  <button @click="approve(r)" :disabled="busy" class="text-emerald-600 hover:underline">Setujui</button>
                  <button @click="reject(r)" :disabled="busy" class="text-red-500 hover:underline ml-3">Tolak</button>
                </template>
                <button v-else-if="r.status !== 'approved' && canManage" @click="del(r)" :disabled="busy" class="text-red-500 hover:underline">Hapus</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal Ajukan Kasbon -->
    <div v-if="showCreate" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="showCreate = false">
      <div class="bg-white w-full max-w-md rounded-2xl p-5">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-slate-800">Ajukan Kasbon</h3>
          <button @click="showCreate = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <label class="block text-xs text-slate-500 mb-1">Karyawan</label>
        <select v-model="form.employee_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm mb-3 outline-none focus:border-brand-500">
          <option value="">— pilih karyawan —</option>
          <option v-for="e in employees" :key="e.id" :value="e.id">{{ e.name }}{{ e.position ? ' · ' + e.position : '' }}</option>
        </select>
        <div class="flex gap-2 mb-3">
          <div class="flex-1">
            <label class="block text-xs text-slate-500 mb-1">Jumlah Kasbon (Rp)</label>
            <input v-model.number="form.amount" type="number" min="0" step="50000" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <div class="w-28">
            <label class="block text-xs text-slate-500 mb-1">Cicil (bulan)</label>
            <input v-model.number="form.months" type="number" min="1" step="1" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
        </div>
        <div v-if="installmentPreview > 0" class="text-sm bg-brand-50 text-brand-700 rounded-lg px-3 py-2 mb-3">
          Potongan otomatis: <b>{{ rupiah(installmentPreview) }}</b> / bulan selama {{ form.months }} bulan.
        </div>
        <input v-model="form.note" placeholder="Catatan (opsional)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm mb-3 outline-none focus:border-brand-500" />
        <p v-if="cErr" class="text-sm text-red-600 mb-2">{{ cErr }}</p>
        <button @click="submitCreate" :disabled="saving" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">
          {{ saving ? 'Mengirim…' : 'Ajukan ke HO' }}
        </button>
      </div>
    </div>
  </div>
</template>
