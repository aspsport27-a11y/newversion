<script setup>
import { ref, onMounted } from 'vue'
import client from '../api/client'

const venues = ref([])
const terminals = ref([])
const cashiers = ref([])
const toast = ref('')

// forms
const showTerminal = ref(false)
const showCashier = ref(false)
const editingTerminal = ref(null)
const editingCashier = ref(null)
const tForm = ref({})
const cForm = ref({})
const err = ref('')
const saving = ref(false)

function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2500) }
function venueName(id) { const v = venues.value.find((x) => x.id === id); return v ? v.code : '—' }

async function loadAll() {
  const [v, t, c] = await Promise.all([
    client.get('/admin/venues'),
    client.get('/admin/terminals'),
    client.get('/admin/cashiers'),
  ])
  venues.value = v.data.venues
  terminals.value = t.data.terminals
  cashiers.value = c.data.cashiers
}
onMounted(loadAll)

// ---- Terminal ----
function openTerminal(t = null) {
  editingTerminal.value = t
  tForm.value = t
    ? { code: t.code, name: t.name, venue_id: t.venue_id, is_active: t.is_active }
    : { code: '', name: '', venue_id: venues.value[0]?.id, is_active: true }
  err.value = ''; showTerminal.value = true
}
async function saveTerminal() {
  saving.value = true; err.value = ''
  try {
    if (editingTerminal.value) await client.put(`/admin/terminals/${editingTerminal.value.id}`, tForm.value)
    else await client.post('/admin/terminals', tForm.value)
    showTerminal.value = false; await loadAll(); flash('Terminal disimpan')
  } catch (e) { err.value = e?.response?.data?.message || 'Gagal.' } finally { saving.value = false }
}
async function delTerminal(t) {
  if (!confirm(`Hapus terminal ${t.code} — ${t.name}?`)) return
  try { await client.delete(`/admin/terminals/${t.id}`); await loadAll(); flash('Terminal dihapus') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal menghapus.') }
}

// ---- Cashier ----
function openCashier(c = null) {
  editingCashier.value = c
  cForm.value = c
    ? { username: c.username, email: c.email, venue_id: c.venue_id, active: c.active }
    : { username: '', email: '', pin: '', venue_id: venues.value[0]?.id }
  err.value = ''; showCashier.value = true
}
async function saveCashier() {
  saving.value = true; err.value = ''
  try {
    if (editingCashier.value) await client.put(`/admin/cashiers/${editingCashier.value.id}`, cForm.value)
    else await client.post('/admin/cashiers', cForm.value)
    showCashier.value = false; await loadAll(); flash('Kasir disimpan')
  } catch (e) { err.value = e?.response?.data?.message || 'Gagal.' } finally { saving.value = false }
}
async function delCashier(c) {
  if (!confirm(`Hapus kasir ${c.username}?`)) return
  try { await client.delete(`/admin/cashiers/${c.id}`); await loadAll(); flash('Kasir dihapus') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal menghapus.') }
}
async function resetPin(u) {
  const pin = prompt(`PIN baru untuk ${u.username}:`)
  if (!pin) return
  try { await client.post(`/admin/cashiers/${u.id}/pin`, { pin }); flash('PIN diperbarui') }
  catch (e) { flash(e?.response?.data?.message || 'Gagal') }
}
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-800 mb-1">Setup Kasir</h1>
    <p class="text-slate-500 mb-6">Kelola terminal POS dan akun kasir per venue.</p>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Terminals -->
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="flex justify-between items-center px-4 py-3 border-b">
          <h3 class="font-semibold text-slate-700">Terminal POS</h3>
          <button @click="openTerminal()" class="bg-brand-600 hover:bg-brand-700 text-white text-xs rounded-lg px-3 py-1.5">+ Terminal</button>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-2 font-medium">Kode</th><th class="px-4 py-2 font-medium">Nama</th>
            <th class="px-4 py-2 font-medium">Venue</th><th class="px-4 py-2 font-medium">Status</th><th class="px-4 py-2"></th>
          </tr></thead>
          <tbody>
            <tr v-if="!terminals.length"><td colspan="5" class="px-4 py-6 text-center text-slate-400">Belum ada terminal.</td></tr>
            <tr v-for="t in terminals" :key="t.id" class="border-t">
              <td class="px-4 py-2 font-mono text-slate-500">{{ t.code }}</td>
              <td class="px-4 py-2 text-slate-700">{{ t.name }}</td>
              <td class="px-4 py-2 text-slate-500">{{ venueName(t.venue_id) }}</td>
              <td class="px-4 py-2">
                <span class="text-xs px-2 py-0.5 rounded-full" :class="t.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'">{{ t.is_active ? 'Aktif' : 'Nonaktif' }}</span>
              </td>
              <td class="px-4 py-2 text-right whitespace-nowrap">
                <button @click="openTerminal(t)" class="text-brand-600 text-xs hover:underline mr-3">Ubah</button>
                <button @click="delTerminal(t)" class="text-red-500 text-xs hover:text-red-700">Hapus</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Cashiers -->
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="flex justify-between items-center px-4 py-3 border-b">
          <h3 class="font-semibold text-slate-700">Kasir</h3>
          <button @click="openCashier()" class="bg-brand-600 hover:bg-brand-700 text-white text-xs rounded-lg px-3 py-1.5">+ Kasir</button>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-2 font-medium">Username</th><th class="px-4 py-2 font-medium">Venue</th>
            <th class="px-4 py-2 font-medium">Status</th><th class="px-4 py-2"></th>
          </tr></thead>
          <tbody>
            <tr v-if="!cashiers.length"><td colspan="4" class="px-4 py-6 text-center text-slate-400">Belum ada kasir.</td></tr>
            <tr v-for="c in cashiers" :key="c.id" class="border-t">
              <td class="px-4 py-2 text-slate-700">{{ c.username }}</td>
              <td class="px-4 py-2 text-slate-500">{{ c.venue_id ? venueName(c.venue_id) : 'semua' }}</td>
              <td class="px-4 py-2">
                <span class="text-xs px-2 py-0.5 rounded-full" :class="c.active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'">{{ c.active ? 'Aktif' : 'Nonaktif' }}</span>
              </td>
              <td class="px-4 py-2 text-right whitespace-nowrap">
                <button @click="resetPin(c)" class="text-brand-600 text-xs hover:underline mr-3">Reset PIN</button>
                <button @click="openCashier(c)" class="text-brand-600 text-xs hover:underline mr-3">Ubah</button>
                <button @click="delCashier(c)" class="text-red-500 text-xs hover:text-red-700">Hapus</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Terminal modal -->
    <div v-if="showTerminal" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-sm rounded-2xl p-5">
        <h3 class="text-lg font-bold text-slate-800 mb-4">{{ editingTerminal ? 'Ubah Terminal' : 'Terminal Baru' }}</h3>
        <div class="space-y-3">
          <input v-model="tForm.code" placeholder="Kode (mis. T-V001-02)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <input v-model="tForm.name" placeholder="Nama terminal" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <select v-model="tForm.venue_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
            <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
          </select>
          <label v-if="editingTerminal" class="flex items-center gap-2 text-sm text-slate-600"><input v-model="tForm.is_active" type="checkbox" /> Aktif</label>
          <p v-if="err" class="text-sm text-red-600">{{ err }}</p>
          <div class="flex gap-2">
            <button @click="saveTerminal" :disabled="saving" class="flex-1 py-2.5 rounded-lg bg-brand-600 text-white font-medium disabled:opacity-50">Simpan</button>
            <button @click="showTerminal = false" class="px-4 py-2.5 rounded-lg bg-slate-100 text-slate-600">Batal</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Cashier modal -->
    <div v-if="showCashier" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-sm rounded-2xl p-5">
        <h3 class="text-lg font-bold text-slate-800 mb-4">{{ editingCashier ? 'Ubah Kasir' : 'Kasir Baru' }}</h3>
        <div class="space-y-3">
          <input v-model="cForm.username" placeholder="Username" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <input v-model="cForm.email" placeholder="Email" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <input v-if="!editingCashier" v-model="cForm.pin" placeholder="PIN (min 4 digit)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <select v-model="cForm.venue_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
            <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
          </select>
          <label v-if="editingCashier" class="flex items-center gap-2 text-sm text-slate-600"><input v-model="cForm.active" type="checkbox" /> Aktif</label>
          <p v-if="editingCashier" class="text-xs text-slate-400">Ganti PIN lewat tombol "Reset PIN".</p>
          <p v-if="err" class="text-sm text-red-600">{{ err }}</p>
          <div class="flex gap-2">
            <button @click="saveCashier" :disabled="saving" class="flex-1 py-2.5 rounded-lg bg-brand-600 text-white font-medium disabled:opacity-50">Simpan</button>
            <button @click="showCashier = false" class="px-4 py-2.5 rounded-lg bg-slate-100 text-slate-600">Batal</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="toast" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
