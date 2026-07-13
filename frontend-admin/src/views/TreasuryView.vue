<script setup>
import { ref, onMounted, computed } from 'vue'
import client from '../api/client'

const tab = ref('accounts')
const venues = ref([])
const accounts = ref([])
const totalBalance = ref(0)
const toast = ref('')
const busy = ref(false)

function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2500) }
function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function venueName(id) { const v = venues.value.find((x) => x.id === id); return v ? v.code : '—' }

async function loadAccounts() {
  const { data } = await client.get('/treasury/accounts')
  accounts.value = data.accounts; totalBalance.value = data.total_balance
}
async function loadVenues() { const { data } = await client.get('/admin/venues'); venues.value = data.venues }
onMounted(async () => { await loadVenues(); await loadAccounts() })

// account form
const showAcc = ref(false)
const editingAcc = ref(null)
const accForm = ref({})
function openAccCreate() { editingAcc.value = null; accForm.value = { name: '', type: 'venue', venue_id: venues.value[0]?.id, bank_name: '', account_number: '', opening_balance: 0 }; showAcc.value = true }
function openAccEdit(a) { editingAcc.value = a; accForm.value = { ...a }; showAcc.value = true }
async function saveAcc() {
  busy.value = true
  try {
    if (editingAcc.value) await client.put(`/treasury/accounts/${editingAcc.value.id}`, accForm.value)
    else await client.post('/treasury/accounts', accForm.value)
    showAcc.value = false; await loadAccounts(); flash('Rekening disimpan')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}

// ledger
const ledger = ref(null)
async function openLedger(a) { const { data } = await client.get(`/treasury/accounts/${a.id}/ledger`); ledger.value = data }

// transfer
const showTransfer = ref(false)
const tForm = ref({})
function openTransfer() { tForm.value = { from_account_id: '', to_account_id: '', amount: null, note: '' }; showTransfer.value = true }
async function doTransfer() {
  busy.value = true
  try { await client.post('/treasury/transfer', tForm.value); showTransfer.value = false; await loadAccounts(); flash('Transfer tercatat') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}

// setoran
const setoranPending = ref({ expected_amount: 0, count: 0 })
const counted = ref(null)
const setoranList = ref([])
async function loadSetoran() {
  const [p, l] = await Promise.all([client.get('/treasury/setoran/pending'), client.get('/treasury/setoran')])
  setoranPending.value = p.data; counted.value = p.data.expected_amount; setoranList.value = l.data.deposits
}
async function doSetoran() {
  busy.value = true
  try { await client.post('/treasury/setoran', { counted_amount: counted.value }); await loadSetoran(); await loadAccounts(); flash('Setoran tercatat') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}

// qris
const qrisList = ref([])
const showQris = ref(false)
const qForm = ref({})
const qSystem = ref(0)
async function loadQris() { const { data } = await client.get('/treasury/qris'); qrisList.value = data.settlements }
function openQris() { const t = new Date(); qForm.value = { venue_id: venues.value[0]?.id, from_date: `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-01`, to_date: t.toISOString().slice(0, 10), actual_amount: null }; qSystem.value = 0; showQris.value = true; fetchSystem() }
async function fetchSystem() {
  if (!qForm.value.venue_id) return
  const { data } = await client.get('/treasury/qris/pos-amount', { params: { venue_id: qForm.value.venue_id, from: qForm.value.from_date, to: qForm.value.to_date } })
  qSystem.value = data.system_amount
}
async function saveQris() {
  busy.value = true
  try { await client.post('/treasury/qris', qForm.value); showQris.value = false; await loadQris(); flash('Rekonsiliasi dibuat') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
async function approveQris(s) {
  try { await client.post(`/treasury/qris/${s.id}/approve`); await loadQris(); await loadAccounts(); flash('QRIS masuk ke rekening venue') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal.') }
}

function switchTab(t) { tab.value = t; if (t === 'setoran') loadSetoran(); if (t === 'qris') loadQris() }
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-800 mb-1">Kas &amp; Bank</h1>
    <p class="text-slate-500 mb-5">Rekening, setoran cash, rekonsiliasi QRIS. Total saldo: <span class="font-semibold text-brand-700">{{ rupiah(totalBalance) }}</span></p>

    <div class="flex gap-1 mb-4 border-b">
      <button @click="switchTab('accounts')" :class="tab === 'accounts' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Rekening</button>
      <button @click="switchTab('setoran')" :class="tab === 'setoran' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Setoran Cash</button>
      <button @click="switchTab('qris')" :class="tab === 'qris' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Rekonsiliasi QRIS</button>
    </div>

    <!-- Rekening -->
    <div v-if="tab === 'accounts'">
      <div class="flex justify-end gap-2 mb-3">
        <button @click="openTransfer" class="bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm rounded-lg px-4 py-2 font-medium">Transfer / Sapu</button>
        <button @click="openAccCreate" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Rekening</button>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        <div v-for="a in accounts" :key="a.id" class="bg-white rounded-xl shadow-sm border p-5">
          <div class="flex justify-between items-start">
            <div>
              <p class="font-semibold text-slate-800">{{ a.name }}</p>
              <p class="text-xs text-slate-400">{{ a.bank_name }} {{ a.account_number }} · {{ a.type === 'holding' ? 'Holding' : venueName(a.venue_id) }}</p>
            </div>
            <span :class="a.type === 'holding' ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-500'" class="text-[10px] rounded px-1.5 py-0.5">{{ a.type }}</span>
          </div>
          <p class="text-2xl font-bold text-slate-800 mt-3">{{ rupiah(a.balance) }}</p>
          <div class="flex gap-3 mt-2">
            <button @click="openLedger(a)" class="text-brand-600 text-xs hover:underline">Buku besar</button>
            <button @click="openAccEdit(a)" class="text-slate-500 text-xs hover:underline">Edit</button>
          </div>
        </div>
        <p v-if="!accounts.length" class="text-slate-400 text-sm">Belum ada rekening. Buat rekening holding & tiap venue.</p>
      </div>
    </div>

    <!-- Setoran -->
    <div v-else-if="tab === 'setoran'">
      <div class="bg-white rounded-xl shadow-sm border p-5 mb-4">
        <p class="text-sm text-slate-500 mb-1">Cash belum disetor ({{ setoranPending.count }} shift)</p>
        <p class="text-2xl font-bold text-slate-800 mb-3">{{ rupiah(setoranPending.expected_amount) }}</p>
        <div v-if="setoranPending.count" class="flex items-end gap-2">
          <div><label class="block text-xs text-slate-500 mb-1">Hitungan fisik (HO)</label>
            <input v-model.number="counted" type="number" class="rounded-lg border border-slate-300 px-3 py-2 text-sm text-right outline-none focus:border-brand-500" /></div>
          <span class="text-sm mb-2" :class="(counted - setoranPending.expected_amount) === 0 ? 'text-emerald-600' : 'text-red-600'">Selisih: {{ rupiah((counted || 0) - setoranPending.expected_amount) }}</span>
          <button @click="doSetoran" :disabled="busy" class="ml-auto bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">Setor ke Holding</button>
        </div>
        <p v-else class="text-sm text-emerald-600">Semua sudah disetor 🎉</p>
      </div>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr><th class="px-4 py-3 font-medium">Kode</th><th class="px-4 py-3 font-medium">Tanggal</th><th class="px-4 py-3 font-medium text-right">Seharusnya</th><th class="px-4 py-3 font-medium text-right">Disetor</th><th class="px-4 py-3 font-medium text-right">Selisih</th></tr></thead>
          <tbody>
            <tr v-if="!setoranList.length"><td colspan="5" class="px-4 py-6 text-center text-slate-400">Belum ada setoran.</td></tr>
            <tr v-for="s in setoranList" :key="s.id" class="border-t">
              <td class="px-4 py-2 font-mono text-xs text-slate-500">{{ s.code }}</td>
              <td class="px-4 py-2 text-slate-600">{{ s.deposit_date }}</td>
              <td class="px-4 py-2 text-right">{{ rupiah(s.expected_amount) }}</td>
              <td class="px-4 py-2 text-right">{{ rupiah(s.counted_amount) }}</td>
              <td class="px-4 py-2 text-right" :class="s.variance === 0 ? 'text-emerald-600' : 'text-red-600'">{{ rupiah(s.variance) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- QRIS -->
    <div v-else>
      <div class="flex justify-end mb-3"><button @click="openQris" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Rekonsiliasi QRIS</button></div>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr><th class="px-4 py-3 font-medium">Venue</th><th class="px-4 py-3 font-medium">Periode</th><th class="px-4 py-3 font-medium text-right">Sistem (POS)</th><th class="px-4 py-3 font-medium text-right">Masuk Bank</th><th class="px-4 py-3 font-medium text-right">Selisih</th><th class="px-4 py-3 font-medium text-center">Status</th><th class="px-4 py-3"></th></tr></thead>
          <tbody>
            <tr v-if="!qrisList.length"><td colspan="7" class="px-4 py-6 text-center text-slate-400">Belum ada rekonsiliasi.</td></tr>
            <tr v-for="s in qrisList" :key="s.id" class="border-t">
              <td class="px-4 py-2 text-slate-700">{{ venueName(s.venue_id) }}</td>
              <td class="px-4 py-2 text-xs text-slate-500">{{ s.from_date }} → {{ s.to_date }}</td>
              <td class="px-4 py-2 text-right">{{ rupiah(s.system_amount) }}</td>
              <td class="px-4 py-2 text-right">{{ rupiah(s.actual_amount) }}</td>
              <td class="px-4 py-2 text-right" :class="s.variance === 0 ? 'text-emerald-600' : 'text-amber-600'">{{ rupiah(s.variance) }}</td>
              <td class="px-4 py-2 text-center"><span :class="s.status === 'approved' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'" class="text-xs rounded-full px-2 py-0.5">{{ s.status === 'approved' ? 'Approved' : 'Draft' }}</span></td>
              <td class="px-4 py-2 text-right"><button v-if="s.status === 'draft'" @click="approveQris(s)" class="text-brand-600 text-sm hover:underline">Approve</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Account modal -->
    <div v-if="showAcc" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-md rounded-2xl p-5">
        <div class="flex justify-between items-center mb-4"><h3 class="text-lg font-bold text-slate-800">{{ editingAcc ? 'Edit Rekening' : 'Rekening Baru' }}</h3><button @click="showAcc = false" class="text-slate-400 text-xl">✕</button></div>
        <div class="space-y-2">
          <input v-model="accForm.name" placeholder="Nama rekening" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <div v-if="!editingAcc" class="grid grid-cols-2 gap-2">
            <select v-model="accForm.type" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500"><option value="venue">Venue</option><option value="holding">Holding</option></select>
            <select v-if="accForm.type === 'venue'" v-model="accForm.venue_id" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500"><option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }}</option></select>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <input v-model="accForm.bank_name" placeholder="Bank" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
            <input v-model="accForm.account_number" placeholder="No. rekening" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <div><label class="block text-xs text-slate-500 mb-1">Saldo awal</label><input v-model.number="accForm.opening_balance" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-right outline-none focus:border-brand-500" /></div>
          <button @click="saveAcc" :disabled="busy" class="w-full mt-2 py-2.5 rounded-lg bg-brand-600 text-white font-medium disabled:opacity-50">Simpan</button>
        </div>
      </div>
    </div>

    <!-- Transfer modal -->
    <div v-if="showTransfer" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-md rounded-2xl p-5">
        <div class="flex justify-between items-center mb-4"><h3 class="text-lg font-bold text-slate-800">Transfer / Sapu</h3><button @click="showTransfer = false" class="text-slate-400 text-xl">✕</button></div>
        <div class="space-y-2">
          <select v-model="tForm.from_account_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500"><option value="">Dari rekening…</option><option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }} ({{ rupiah(a.balance) }})</option></select>
          <select v-model="tForm.to_account_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500"><option value="">Ke rekening…</option><option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option></select>
          <input v-model.number="tForm.amount" type="number" placeholder="Jumlah" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-right outline-none focus:border-brand-500" />
          <button @click="doTransfer" :disabled="busy" class="w-full mt-2 py-2.5 rounded-lg bg-brand-600 text-white font-medium disabled:opacity-50">Transfer</button>
        </div>
      </div>
    </div>

    <!-- QRIS modal -->
    <div v-if="showQris" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-md rounded-2xl p-5">
        <div class="flex justify-between items-center mb-4"><h3 class="text-lg font-bold text-slate-800">Rekonsiliasi QRIS</h3><button @click="showQris = false" class="text-slate-400 text-xl">✕</button></div>
        <div class="space-y-2">
          <select v-model="qForm.venue_id" @change="fetchSystem" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500"><option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option></select>
          <div class="grid grid-cols-2 gap-2">
            <input v-model="qForm.from_date" @change="fetchSystem" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
            <input v-model="qForm.to_date" @change="fetchSystem" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <div class="flex justify-between text-sm bg-slate-50 rounded-lg px-3 py-2"><span class="text-slate-500">QRIS di sistem (POS)</span><span class="font-medium">{{ rupiah(qSystem) }}</span></div>
          <div><label class="block text-xs text-slate-500 mb-1">Yang masuk rekening bank</label><input v-model.number="qForm.actual_amount" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-right outline-none focus:border-brand-500" /></div>
          <button @click="saveQris" :disabled="busy" class="w-full mt-2 py-2.5 rounded-lg bg-brand-600 text-white font-medium disabled:opacity-50">Buat (draft)</button>
        </div>
      </div>
    </div>

    <!-- Ledger modal -->
    <div v-if="ledger" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="ledger = null">
      <div class="bg-white w-full max-w-lg rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-center mb-1"><h3 class="text-lg font-bold text-slate-800">{{ ledger.account.name }}</h3><button @click="ledger = null" class="text-slate-400 text-xl">✕</button></div>
        <p class="text-xl font-bold text-brand-700 mb-3">{{ rupiah(ledger.account.balance) }}</p>
        <table class="w-full text-sm">
          <thead class="text-slate-400 text-xs text-left"><tr><th class="py-1">Tanggal</th><th class="py-1">Jenis</th><th class="py-1 text-right">Nominal</th></tr></thead>
          <tbody>
            <tr v-if="!ledger.transactions.length"><td colspan="3" class="py-4 text-center text-slate-400">Belum ada mutasi.</td></tr>
            <tr v-for="t in ledger.transactions" :key="t.id" class="border-t">
              <td class="py-1.5 text-slate-500">{{ t.tx_date }}</td>
              <td class="py-1.5 text-slate-600">{{ t.kind }} <span class="text-xs text-slate-400">{{ t.note }}</span></td>
              <td class="py-1.5 text-right font-medium" :class="t.direction === 'in' ? 'text-emerald-600' : 'text-red-600'">{{ t.direction === 'in' ? '+' : '-' }}{{ rupiah(t.amount) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="toast" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
