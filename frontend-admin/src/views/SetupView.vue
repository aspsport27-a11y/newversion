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

function openTerminal() {
  tForm.value = { code: '', name: '', venue_id: venues.value[0]?.id }
  err.value = ''; showTerminal.value = true
}
async function saveTerminal() {
  saving.value = true; err.value = ''
  try {
    await client.post('/admin/terminals', tForm.value)
    showTerminal.value = false; await loadAll(); flash('Terminal dibuat')
  } catch (e) { err.value = e?.response?.data?.message || 'Gagal.' } finally { saving.value = false }
}

function openCashier() {
  cForm.value = { username: '', email: '', pin: '', venue_id: venues.value[0]?.id }
  err.value = ''; showCashier.value = true
}
async function saveCashier() {
  saving.value = true; err.value = ''
  try {
    await client.post('/admin/cashiers', cForm.value)
    showCashier.value = false; await loadAll(); flash('Kasir dibuat')
  } catch (e) { err.value = e?.response?.data?.message || 'Gagal.' } finally { saving.value = false }
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
          <button @click="openTerminal" class="bg-brand-600 hover:bg-brand-700 text-white text-xs rounded-lg px-3 py-1.5">+ Terminal</button>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-2 font-medium">Kode</th><th class="px-4 py-2 font-medium">Nama</th><th class="px-4 py-2 font-medium">Venue</th>
          </tr></thead>
          <tbody>
            <tr v-if="!terminals.length"><td colspan="3" class="px-4 py-6 text-center text-slate-400">Belum ada terminal.</td></tr>
            <tr v-for="t in terminals" :key="t.id" class="border-t">
              <td class="px-4 py-2 font-mono text-slate-500">{{ t.code }}</td>
              <td class="px-4 py-2 text-slate-700">{{ t.name }}</td>
              <td class="px-4 py-2 text-slate-500">{{ venueName(t.venue_id) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Cashiers -->
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="flex justify-between items-center px-4 py-3 border-b">
          <h3 class="font-semibold text-slate-700">Kasir</h3>
          <button @click="openCashier" class="bg-brand-600 hover:bg-brand-700 text-white text-xs rounded-lg px-3 py-1.5">+ Kasir</button>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-2 font-medium">Username</th><th class="px-4 py-2 font-medium">Venue</th><th class="px-4 py-2"></th>
          </tr></thead>
          <tbody>
            <tr v-if="!cashiers.length"><td colspan="3" class="px-4 py-6 text-center text-slate-400">Belum ada kasir.</td></tr>
            <tr v-for="c in cashiers" :key="c.id" class="border-t">
              <td class="px-4 py-2 text-slate-700">{{ c.username }}</td>
              <td class="px-4 py-2 text-slate-500">{{ c.venue_id ? venueName(c.venue_id) : 'semua' }}</td>
              <td class="px-4 py-2 text-right"><button @click="resetPin(c)" class="text-brand-600 text-xs hover:underline">Reset PIN</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Terminal modal -->
    <div v-if="showTerminal" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-sm rounded-2xl p-5">
        <h3 class="text-lg font-bold text-slate-800 mb-4">Terminal Baru</h3>
        <div class="space-y-3">
          <input v-model="tForm.code" placeholder="Kode (mis. T-V001-02)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <input v-model="tForm.name" placeholder="Nama terminal" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <select v-model="tForm.venue_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
            <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
          </select>
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
        <h3 class="text-lg font-bold text-slate-800 mb-4">Kasir Baru</h3>
        <div class="space-y-3">
          <input v-model="cForm.username" placeholder="Username" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <input v-model="cForm.email" placeholder="Email" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <input v-model="cForm.pin" placeholder="PIN (min 4 digit)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <select v-model="cForm.venue_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
            <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
          </select>
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
