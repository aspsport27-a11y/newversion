<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isManager = computed(() => auth.user?.role === 'manager_unit')

const venues = ref([])
const areas = ref([])
const venueId = ref('')
const employees = ref([])
const positions = ref([])
const loading = ref(false)
const toast = ref('')

// form karyawan
const showForm = ref(false)
const editing = ref(null)
const form = ref({})
const error = ref('')
const saving = ref(false)

// detail (kasbon + akun)
const detail = ref(null)
const debtForm = ref({ type: 'advance', amount: null, note: '' })
const acctForm = ref({ username: '', role: 'staff', pin: '', password: '', area_id: '' })
const busy = ref(false)

function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2500) }
function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function venueCode(id) { const v = venues.value.find((x) => x.id === id); return v ? v.code : '—' }

async function loadVenues() {
  const { data } = await client.get('/admin/venues')
  venues.value = data.venues
  if (!isManager.value && venues.value.length && !venueId.value) venueId.value = venues.value[0].id
  if (!isManager.value) {
    try { areas.value = (await client.get('/admin/areas')).data.areas } catch { /* ignore */ }
  }
}
async function load() {
  loading.value = true
  const params = {}
  if (!isManager.value && venueId.value) params.venue_id = venueId.value
  try {
    const { data } = await client.get('/admin/employees', { params })
    employees.value = data.employees
    positions.value = data.positions
  } finally { loading.value = false }
}
onMounted(async () => { await loadVenues(); await load() })
watch(venueId, load)

function openCreate() {
  editing.value = null
  form.value = { name: '', position: 'Kasir', venue_id: venueId.value || venues.value[0]?.id, salary: null, allowance: null, bank_name: '', bank_account: '', phone: '', email: '', identity_number: '', hire_date: '', status: 'active' }
  error.value = ''; showForm.value = true
}
function openEdit(e) {
  editing.value = e
  form.value = { ...e, hire_date: e.hire_date || '' }
  error.value = ''; showForm.value = true
}
async function save() {
  saving.value = true; error.value = ''
  try {
    const payload = { ...form.value, hire_date: form.value.hire_date || null }
    if (editing.value) await client.put(`/admin/employees/${editing.value.id}`, payload)
    else await client.post('/admin/employees', payload)
    showForm.value = false; await load()
    flash(editing.value ? 'Karyawan diperbarui' : 'Karyawan ditambahkan')
  } catch (e) { error.value = e?.response?.data?.message || 'Gagal.' } finally { saving.value = false }
}
async function remove(e) {
  if (!window.confirm(`Hapus karyawan "${e.name}"?`)) return
  try { await client.delete(`/admin/employees/${e.id}`); await load(); flash('Karyawan dihapus') }
  catch (err) { alert(err?.response?.data?.message || 'Gagal.') }
}

async function openDetail(e) {
  const { data } = await client.get(`/admin/employees/${e.id}`)
  detail.value = data.employee
  debtForm.value = { type: 'advance', amount: null, note: '' }
  acctForm.value = { username: (e.name || '').toLowerCase().replace(/\s+/g, ''), role: 'staff', pin: '', password: '', area_id: '' }
}
async function reloadDetail() {
  const { data } = await client.get(`/admin/employees/${detail.value.id}`)
  detail.value = data.employee
}
async function addDebt() {
  busy.value = true
  try {
    await client.post(`/admin/employees/${detail.value.id}/debt`, { ...debtForm.value })
    debtForm.value = { type: 'advance', amount: null, note: '' }
    await reloadDetail(); await load()
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
async function saveInstallment() {
  busy.value = true
  try {
    await client.put(`/admin/employees/${detail.value.id}`, { kasbon_installment: detail.value.kasbon_installment || null })
    await load(); flash('Cicilan kasbon disimpan')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
async function createAccount() {
  busy.value = true
  try {
    await client.post(`/admin/employees/${detail.value.id}/account`, { ...acctForm.value })
    await reloadDetail(); await load(); flash('Akun login dibuat')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
async function disconnectAccount() {
  if (!confirm(`Putuskan akun "${detail.value.account.username}" dari ${detail.value.name}? Akun tak bisa login lagi.`)) return
  busy.value = true
  try {
    const { data } = await client.delete(`/admin/employees/${detail.value.id}/account`)
    await reloadDetail(); await load(); flash(data.message || 'Akun diputuskan')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
const resetCred = ref('')
async function resetAccount() {
  const isStaff = detail.value?.account?.role === 'staff'
  if (isStaff ? resetCred.value.length < 4 : resetCred.value.length < 8) {
    alert(isStaff ? 'PIN minimal 4 digit' : 'Password minimal 8 karakter'); return
  }
  busy.value = true
  try {
    const body = isStaff ? { pin: resetCred.value } : { password: resetCred.value }
    const { data } = await client.post(`/admin/employees/${detail.value.id}/account/reset`, body)
    resetCred.value = ''; flash(data.message || 'Kredensial diperbarui')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-6">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">Karyawan</h1>
        <p class="text-slate-500 mt-1">Data karyawan, kasbon/piutang, dan akun login.</p>
      </div>
      <div class="flex gap-2">
        <select v-if="!isManager" v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select>
        <button @click="openCreate" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Karyawan</button>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th class="px-4 py-3 font-medium">Kode</th>
              <th class="px-4 py-3 font-medium">Nama</th>
              <th class="px-4 py-3 font-medium">Jabatan</th>
              <th class="px-4 py-3 font-medium text-right">Gaji pokok</th>
              <th class="px-4 py-3 font-medium text-right">Kasbon</th>
              <th class="px-4 py-3 font-medium text-center">Akun</th>
              <th class="px-4 py-3 font-medium text-center">Status</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading"><td colspan="8" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!employees.length"><td colspan="8" class="px-4 py-8 text-center text-slate-400">Belum ada karyawan.</td></tr>
            <tr v-for="e in employees" :key="e.id" class="border-t hover:bg-slate-50">
              <td class="px-4 py-3 font-mono text-slate-500">{{ e.employee_id }}</td>
              <td class="px-4 py-3 font-medium text-slate-700">{{ e.name }}</td>
              <td class="px-4 py-3"><span class="text-xs bg-brand-50 text-brand-700 rounded px-2 py-0.5">{{ e.position || '—' }}</span></td>
              <td class="px-4 py-3 text-right text-slate-600">{{ e.salary != null ? rupiah(e.salary) : '—' }}</td>
              <td class="px-4 py-3 text-right" :class="e.debt_balance > 0 ? 'text-amber-600 font-medium' : 'text-slate-400'">{{ rupiah(e.debt_balance) }}</td>
              <td class="px-4 py-3 text-center">
                <span v-if="e.has_account" class="text-xs bg-emerald-100 text-emerald-700 rounded-full px-2 py-0.5">{{ e.username }}</span>
                <span v-else class="text-xs text-slate-400">—</span>
              </td>
              <td class="px-4 py-3 text-center">
                <span :class="e.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="text-xs rounded-full px-2 py-0.5">{{ e.status }}</span>
              </td>
              <td class="px-4 py-3 text-right whitespace-nowrap">
                <button @click="openDetail(e)" class="text-slate-600 text-sm hover:underline">Kasbon/Akun</button>
                <button @click="openEdit(e)" class="text-brand-600 text-sm hover:underline ml-3">Edit</button>
                <button @click="remove(e)" class="text-red-500 text-sm hover:underline ml-3">Hapus</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Form karyawan -->
    <div v-if="showForm" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-lg rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-slate-800">{{ editing ? 'Edit Karyawan' : 'Karyawan Baru' }}</h3>
          <button @click="showForm = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div class="col-span-2"><label class="block text-xs text-slate-500 mb-1">Nama *</label>
            <input v-model="form.name" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Jabatan</label>
            <select v-model="form.position" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option v-for="p in positions" :key="p" :value="p">{{ p }}</option>
            </select></div>
          <div v-if="!isManager"><label class="block text-xs text-slate-500 mb-1">Venue</label>
            <select v-model="form.venue_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }}</option>
            </select>
            <p v-if="editing?.has_account && form.venue_id !== editing.venue_id" class="text-xs text-amber-600 mt-1">Akun login "{{ editing.username }}" ikut dipindah ke venue ini.</p></div>
          <div><label class="block text-xs text-slate-500 mb-1">Gaji pokok</label>
            <input v-model.number="form.salary" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Tunjangan tetap</label>
            <input v-model.number="form.allowance" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Bank</label>
            <input v-model="form.bank_name" placeholder="BRI/BCA…" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">No. Rekening</label>
            <input v-model="form.bank_account" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Telepon</label>
            <input v-model="form.phone" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">No. KTP</label>
            <input v-model="form.identity_number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Tgl masuk</label>
            <input v-model="form.hire_date" type="date" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div v-if="editing"><label class="block text-xs text-slate-500 mb-1">Status</label>
            <select v-model="form.status" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option value="active">active</option><option value="resign">resign</option>
            </select></div>
        </div>
        <p v-if="error" class="text-sm text-red-600 mt-3">{{ error }}</p>
        <button @click="save" :disabled="saving" class="w-full mt-4 py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">{{ saving ? 'Menyimpan…' : 'Simpan' }}</button>
      </div>
    </div>

    <!-- Detail: kasbon + akun -->
    <div v-if="detail" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="detail = null">
      <div class="bg-white w-full max-w-md rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-center mb-3">
          <h3 class="text-lg font-bold text-slate-800">{{ detail.name }}</h3>
          <button @click="detail = null" class="text-slate-400 text-xl">✕</button>
        </div>
        <p class="text-sm text-slate-500 mb-4">{{ detail.employee_id }} · {{ detail.position }}</p>

        <!-- Kasbon -->
        <div class="bg-slate-50 rounded-lg p-3 mb-3">
          <div class="flex justify-between items-center mb-2">
            <span class="text-sm font-medium text-slate-700">Kasbon / Piutang</span>
            <span class="font-bold" :class="detail.debt_balance > 0 ? 'text-amber-600' : 'text-emerald-600'">{{ rupiah(detail.debt_balance) }}</span>
          </div>
          <div class="flex items-center gap-2 mb-2 text-sm">
            <span class="text-slate-500 whitespace-nowrap">Cicilan/bulan:</span>
            <input v-model.number="detail.kasbon_installment" type="number" placeholder="0" class="w-28 rounded-lg border border-slate-300 px-2 py-1 text-sm text-right outline-none" />
            <button @click="saveInstallment" :disabled="busy" class="text-brand-600 text-xs hover:underline">Simpan</button>
            <span v-if="detail.kasbon_installment > 0 && detail.debt_balance > 0" class="text-xs text-slate-400 ml-auto">≈ {{ Math.ceil(detail.debt_balance / detail.kasbon_installment) }} bln lunas</span>
          </div>
          <div class="flex gap-2">
            <select v-model="debtForm.type" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none">
              <option value="advance">Kasbon (+)</option>
              <option value="repayment">Bayar/Potong (−)</option>
            </select>
            <input v-model.number="debtForm.amount" type="number" placeholder="Jumlah" class="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none" />
            <button @click="addDebt" :disabled="busy || !debtForm.amount" class="bg-brand-600 text-white rounded-lg px-3 text-sm disabled:opacity-50">Catat</button>
          </div>
          <input v-model="debtForm.note" placeholder="Catatan (opsional)" class="w-full mt-2 rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none" />
          <div class="mt-2 max-h-32 overflow-auto">
            <div v-for="x in detail.debts" :key="x.id" class="flex justify-between text-xs py-1 border-t">
              <span :class="x.type === 'advance' ? 'text-amber-600' : 'text-emerald-600'">{{ x.type === 'advance' ? 'Kasbon' : 'Bayar' }} <span class="text-slate-400">{{ x.note }}</span></span>
              <span>{{ x.type === 'advance' ? '+' : '−' }}{{ rupiah(x.amount) }}</span>
            </div>
          </div>
        </div>

        <!-- Akun login -->
        <div class="bg-slate-50 rounded-lg p-3">
          <p class="text-sm font-medium text-slate-700 mb-2">Akun Login</p>
          <div v-if="detail.account" class="space-y-2">
            <p class="text-sm text-emerald-700">✓ {{ detail.account.username }} ({{ detail.account.role }})</p>
            <div class="flex gap-2">
              <input v-model="resetCred" :type="detail.account.role === 'staff' ? 'text' : 'text'"
                :placeholder="detail.account.role === 'staff' ? 'PIN baru (min 4)' : 'Password baru (min 8)'"
                class="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none" />
              <button @click="resetAccount" :disabled="busy" class="rounded-lg bg-slate-700 hover:bg-slate-800 text-white text-sm px-3 py-1.5 font-medium disabled:opacity-50">
                {{ detail.account.role === 'staff' ? 'Reset PIN' : 'Ganti Password' }}
              </button>
            </div>
            <button @click="disconnectAccount" :disabled="busy" class="text-xs text-red-500 hover:text-red-700">Putuskan akun (agar karyawan bisa dihapus)</button>
          </div>
          <div v-else class="space-y-2">
            <div class="flex gap-2">
              <input v-model="acctForm.username" placeholder="username" class="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none" />
              <select v-model="acctForm.role" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none">
                <option value="staff">Kasir (PIN)</option>
                <option value="staff">Ass. Manager/SPV (PIN)</option>
                <option value="manager_unit">Manager</option>
                <option v-if="!isManager" value="admin_unit">Admin Unit (area)</option>
                <option v-if="!isManager" value="head_office">Head Office</option>
              </select>
            </div>
            <select v-if="acctForm.role === 'admin_unit'" v-model="acctForm.area_id" class="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none">
              <option value="">— pilih area —</option>
              <option v-for="a in areas" :key="a.id" :value="a.id">{{ a.code }} — {{ a.name }} ({{ a.venue_count }} venue)</option>
            </select>
            <input v-if="acctForm.role === 'staff'" v-model="acctForm.pin" placeholder="PIN (min 4 digit)" class="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none" />
            <input v-else v-model="acctForm.password" type="text" placeholder="Password (min 8 karakter)" class="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none" />
            <button @click="createAccount" :disabled="busy" class="w-full py-2 rounded-lg bg-brand-600 text-white text-sm font-medium disabled:opacity-50">Buatkan Akun</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="toast" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
