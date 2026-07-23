<script setup>
import { ref, onMounted, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isManager = computed(() => auth.user?.role === 'manager_unit')
const isAdminUnit = computed(() => auth.user?.role === 'admin_unit')
const isApprover = computed(() => ['admin', 'head_office'].includes(auth.user?.role))
const canRevertPo = computed(() => auth.hasPerm('proc.pay'))

const venues = ref([])
const venueId = ref('')
const suppliers = ref([])
const accounts = ref([])
const sourceAccount = ref('')
const pos = ref([])
const statusFilter = ref('')
const loading = ref(false)
const toast = ref('')
function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2500) }
function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }

const statusMap = {
  submitted: ['Menunggu', 'bg-amber-100 text-amber-700'],
  approved: ['Disetujui', 'bg-blue-100 text-blue-700'],
  received: ['Diterima', 'bg-violet-100 text-violet-700'],
  paid: ['Dibayar', 'bg-emerald-100 text-emerald-700'],
  rejected: ['Ditolak', 'bg-red-100 text-red-600'],
}
function venueName(id) { const v = venues.value.find((x) => x.id === id); return v ? v.code : '—' }

async function loadBase() {
  const [v, s] = await Promise.all([client.get('/venues'), client.get('/procurement/suppliers')])
  venues.value = v.data.venues
  if (isManager.value) { venues.value = venues.value.filter((x) => x.id === auth.user?.venue_id); venueId.value = auth.user?.venue_id || '' }
  else if (isAdminUnit.value) venues.value = venues.value.filter((x) => x.area_id === auth.user?.area_id)
  suppliers.value = s.data.suppliers
  if (isApprover.value) {
    try {
      const { data } = await client.get('/treasury/accounts')
      accounts.value = data.accounts
      sourceAccount.value = data.accounts.find((a) => a.type === 'holding')?.id || data.accounts[0]?.id || ''
    } catch (_) { /* ignore */ }
  }
}
async function loadPo() {
  loading.value = true
  const params = { kind: 'ops' }
  if (!isManager.value && venueId.value) params.venue_id = venueId.value
  if (statusFilter.value) params.status = statusFilter.value
  try { const { data } = await client.get('/procurement/pos', { params }); pos.value = data.pos }
  finally { loading.value = false }
}

// ---- Create ----
const showCreate = ref(false)
const cForm = ref({ venue_id: '', supplier_id: '', notes: '', items: [] })
const cFiles = ref([])
const cErr = ref('')
const saving = ref(false)
const cTotal = computed(() => cForm.value.items.reduce((s, i) => s + (Number(i.quantity) || 0) * (Number(i.unit_price) || 0), 0))
function newItem() { return { item_name: '', quantity: 1, unit: 'pcs', unit_price: null, note: '' } }
function openCreate() {
  cForm.value = { venue_id: isManager.value ? auth.user?.venue_id : (venueId.value || venues.value[0]?.id), supplier_id: '', notes: '', items: [newItem()] }
  cFiles.value = []; cErr.value = ''; showCreate.value = true
}
function addRow() { cForm.value.items.push(newItem()) }
function rmRow(i) { cForm.value.items.splice(i, 1) }
function onFiles(e) { cFiles.value = Array.from(e.target.files) }
async function submitCreate() {
  cErr.value = ''
  if (!cForm.value.items.length || cForm.value.items.some((i) => !i.item_name || !(Number(i.quantity) > 0))) {
    cErr.value = 'Isi nama & qty tiap item.'; return
  }
  saving.value = true
  try {
    const payload = {
      kind: 'ops', supplier_id: cForm.value.supplier_id || null, notes: cForm.value.notes,
      items: cForm.value.items.map((i) => ({ item_name: i.item_name, quantity: i.quantity, unit: i.unit, unit_price: i.unit_price, note: i.note })),
    }
    if (!isManager.value) payload.venue_id = cForm.value.venue_id
    const { data } = await client.post('/procurement/pos', payload)
    for (const f of cFiles.value) { const fd = new FormData(); fd.append('file', f); await client.post(`/procurement/pos/${data.po.id}/attachment`, fd, { headers: { 'Content-Type': 'multipart/form-data' } }) }
    showCreate.value = false; await loadPo(); flash('Pembelian ops dibuat')
  } catch (e) { cErr.value = e?.response?.data?.message || 'Gagal.' } finally { saving.value = false }
}

// ---- Detail & actions ----
const detail = ref(null)
const busy = ref(false)
async function openDetail(p) { const { data } = await client.get(`/procurement/pos/${p.id}`); detail.value = data.po }
async function act(action, extra = {}) {
  busy.value = true
  try {
    await client.post(`/procurement/pos/${detail.value.id}/${action}`, extra)
    const { data } = await client.get(`/procurement/pos/${detail.value.id}`); detail.value = data.po
    await loadPo(); flash('Berhasil')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
async function doReject() {
  const reason = window.prompt('Alasan penolakan?'); if (reason === null) return
  await act('reject', { reason })
}
async function revertPo() {
  if (!window.confirm('Batalkan proses & kembalikan ke Menunggu? (kalau sudah dibayar, kas dikembalikan)')) return
  await act('revert')
}
function canDeletePo(p) { return ['submitted', 'rejected'].includes(p.status) }
async function removePo(p) {
  if (!window.confirm(`Hapus pembelian ${p.code}?`)) return
  busy.value = true
  try { await client.delete(`/procurement/pos/${p.id}`); detail.value = null; await loadPo(); flash('Dihapus') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
async function viewAtt(a) { const res = await client.get(`/procurement/attachments/${a.id}`, { responseType: 'blob' }); window.open(URL.createObjectURL(res.data), '_blank') }
const proofInput = ref(null); const uploadingProof = ref(false)
function triggerProof() { proofInput.value?.click() }
async function onProof(e) {
  const f = e.target.files[0]; if (!f) return
  uploadingProof.value = true
  try {
    const fd = new FormData(); fd.append('file', f)
    await client.post(`/procurement/pos/${detail.value.id}/attachment`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    const { data } = await client.get(`/procurement/pos/${detail.value.id}`); detail.value = data.po
  } catch (err) { alert('Gagal upload.') } finally { uploadingProof.value = false; e.target.value = '' }
}

onMounted(async () => { await loadBase(); await loadPo() })
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-1">
      <h1 class="text-2xl font-bold text-slate-800">Procurement Ops</h1>
      <button @click="openCreate" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Pembelian Ops</button>
    </div>
    <p class="text-slate-500 mb-5">Pembelian keperluan rumah tangga / operasional venue. Alur sama dengan Procurement (buat → setujui → terima → bayar HO), tapi <b>tidak menjadi stok jual</b> — hanya record.</p>

    <div class="bg-white rounded-xl shadow-sm border p-4 mb-5 flex flex-wrap items-end gap-3">
      <div v-if="!isManager"><label class="block text-xs text-slate-500 mb-1">Venue</label>
        <select v-model="venueId" @change="loadPo" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua venue (cakupan saya)</option>
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select></div>
      <div><label class="block text-xs text-slate-500 mb-1">Status</label>
        <select v-model="statusFilter" @change="loadPo" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua status</option>
          <option value="submitted">Menunggu</option><option value="approved">Disetujui</option>
          <option value="received">Diterima</option><option value="paid">Dibayar</option><option value="rejected">Ditolak</option>
        </select></div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-3 font-medium">Kode</th>
            <th class="px-4 py-3 font-medium">Venue</th>
            <th class="px-4 py-3 font-medium">Supplier</th>
            <th class="px-4 py-3 font-medium">Keterangan</th>
            <th class="px-4 py-3 font-medium text-right">Total</th>
            <th class="px-4 py-3 font-medium text-center">Status</th>
          </tr></thead>
          <tbody>
            <tr v-if="loading"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!pos.length"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Belum ada pembelian ops.</td></tr>
            <tr v-for="p in pos" :key="p.id" @click="openDetail(p)" class="border-t hover:bg-slate-50 cursor-pointer">
              <td class="px-4 py-3 font-mono text-xs text-slate-500">{{ p.code }}</td>
              <td class="px-4 py-3 text-slate-600">{{ venueName(p.venue_id) }}</td>
              <td class="px-4 py-3 text-slate-600">{{ p.supplier_name || '—' }}</td>
              <td class="px-4 py-3 text-slate-500 text-xs truncate max-w-[220px]">{{ p.notes || '—' }}</td>
              <td class="px-4 py-3 text-right font-medium">{{ rupiah(p.total_amount) }}</td>
              <td class="px-4 py-3 text-center"><span :class="statusMap[p.status]?.[1]" class="text-xs rounded-full px-2 py-0.5">{{ statusMap[p.status]?.[0] }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Create modal -->
    <div v-if="showCreate" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-lg rounded-2xl p-5 max-h-[92vh] overflow-auto">
        <div class="flex justify-between items-center mb-4"><h3 class="text-lg font-bold text-slate-800">Pembelian Ops Baru</h3><button @click="showCreate = false" class="text-slate-400 text-xl">✕</button></div>
        <div class="space-y-3">
          <div v-if="!isManager">
            <label class="block text-xs text-slate-500 mb-1">Venue</label>
            <select v-model="cForm.venue_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
            </select>
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Supplier / Toko (opsional)</label>
            <select v-model="cForm.supplier_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option value="">— tanpa supplier —</option>
              <option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>
          <div>
            <div class="flex items-center justify-between mb-1"><label class="text-xs text-slate-500">Item pembelian</label>
              <button @click="addRow" class="text-xs text-brand-600 hover:underline">+ Tambah item</button></div>
            <div v-for="(it, i) in cForm.items" :key="i" class="grid grid-cols-12 gap-1.5 mb-1.5">
              <input v-model="it.item_name" placeholder="Nama barang" class="col-span-5 rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-brand-500" />
              <input v-model.number="it.quantity" type="number" min="1" placeholder="Qty" class="col-span-2 rounded-lg border border-slate-300 px-2 py-1.5 text-sm text-right outline-none focus:border-brand-500" />
              <input v-model="it.unit" placeholder="unit" class="col-span-2 rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-brand-500" />
              <input v-model.number="it.unit_price" type="number" min="0" placeholder="Harga" class="col-span-2 rounded-lg border border-slate-300 px-2 py-1.5 text-sm text-right outline-none focus:border-brand-500" />
              <button @click="rmRow(i)" class="col-span-1 text-red-400 text-sm">✕</button>
            </div>
            <p class="text-right text-sm font-semibold text-slate-700">Total: {{ rupiah(cTotal) }}</p>
          </div>
          <textarea v-model="cForm.notes" placeholder="Keterangan (opsional)" rows="2" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500"></textarea>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Nota / bukti (opsional)</label>
            <input type="file" accept="image/*,.pdf" multiple @change="onFiles" class="text-xs" />
          </div>
          <p v-if="cErr" class="text-sm text-red-600">{{ cErr }}</p>
          <button @click="submitCreate" :disabled="saving" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">{{ saving ? 'Menyimpan…' : 'Buat Pembelian' }}</button>
        </div>
      </div>
    </div>

    <!-- Detail modal -->
    <div v-if="detail" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="detail = null">
      <div class="bg-white w-full max-w-md rounded-2xl p-5 max-h-[92vh] overflow-auto">
        <div class="flex justify-between items-center mb-1"><h3 class="text-lg font-bold text-slate-800 font-mono">{{ detail.code }}</h3><button @click="detail = null" class="text-slate-400 text-xl">✕</button></div>
        <p class="text-sm text-slate-500 mb-3">{{ venueName(detail.venue_id) }} · {{ detail.supplier_name || 'tanpa supplier' }}</p>
        <div class="border rounded-lg overflow-hidden mb-3">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left text-xs"><tr><th class="px-3 py-2">Item</th><th class="px-3 py-2 text-right">Qty</th><th class="px-3 py-2 text-right">Subtotal</th></tr></thead>
            <tbody>
              <tr v-for="it in detail.items" :key="it.id" class="border-t">
                <td class="px-3 py-2 text-slate-700">{{ it.item_name }}</td>
                <td class="px-3 py-2 text-right">{{ it.quantity }} {{ it.unit }}</td>
                <td class="px-3 py-2 text-right">{{ rupiah(it.total_price) }}</td>
              </tr>
            </tbody>
            <tfoot><tr class="border-t bg-slate-50 font-semibold"><td class="px-3 py-2" colspan="2">Total</td><td class="px-3 py-2 text-right">{{ rupiah(detail.total_amount) }}</td></tr></tfoot>
          </table>
        </div>
        <p v-if="detail.notes" class="text-sm text-slate-500 mb-2">{{ detail.notes }}</p>
        <div v-if="detail.rejection_reason" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">Ditolak: {{ detail.rejection_reason }}</div>

        <div class="mb-3">
          <div class="flex items-center justify-between mb-1">
            <p class="text-xs font-medium text-slate-500">Nota / bukti</p>
            <input ref="proofInput" type="file" accept="image/*,.pdf" class="hidden" @change="onProof" />
            <button @click="triggerProof" :disabled="uploadingProof" class="text-xs text-brand-600 hover:underline disabled:opacity-50">{{ uploadingProof ? 'Mengunggah…' : '+ Upload' }}</button>
          </div>
          <div v-if="!detail.attachments.length" class="text-sm text-slate-400">Tidak ada lampiran.</div>
          <div v-else class="flex flex-wrap gap-2"><button v-for="a in detail.attachments" :key="a.id" @click="viewAtt(a)" class="text-xs bg-slate-100 hover:bg-slate-200 text-slate-600 rounded px-2 py-1">📎 {{ a.filename }}</button></div>
        </div>

        <div class="flex gap-2 pt-2 border-t">
          <template v-if="detail.status === 'submitted'">
            <button @click="act('approve')" :disabled="busy" class="flex-1 py-2.5 rounded-lg bg-emerald-600 text-white font-medium disabled:opacity-50">Setujui</button>
            <button @click="doReject" :disabled="busy" class="flex-1 py-2.5 rounded-lg bg-red-600 text-white font-medium disabled:opacity-50">Tolak</button>
          </template>
          <button v-else-if="detail.status === 'approved'" @click="act('receive')" :disabled="busy" class="w-full py-2.5 rounded-lg bg-violet-600 text-white font-medium disabled:opacity-50">Barang Diterima</button>
          <template v-else-if="detail.status === 'received' && isApprover">
            <div class="w-full">
              <label class="block text-xs text-slate-500 mb-1">Sumber dana</label>
              <select v-model="sourceAccount" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500 mb-2">
                <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }} ({{ rupiah(a.balance) }})</option>
              </select>
              <button @click="act('pay', { source_account_id: sourceAccount })" :disabled="busy" class="w-full py-2.5 rounded-lg bg-brand-600 text-white font-medium disabled:opacity-50">Bayar</button>
            </div>
          </template>
          <p v-else class="text-sm text-slate-400 py-2 text-center w-full">Status: {{ statusMap[detail.status]?.[0] }}<span v-if="detail.status === 'received'"> — menunggu pembayaran HO</span></p>
        </div>
        <div v-if="detail.status !== 'submitted' && canRevertPo" class="flex gap-2 pt-2">
          <button @click="revertPo" :disabled="busy" class="flex-1 py-2 rounded-lg bg-amber-50 hover:bg-amber-100 text-amber-700 font-medium disabled:opacity-50">↩️ Batal Proses</button>
        </div>
        <div v-if="canDeletePo(detail)" class="flex gap-2 pt-2">
          <button @click="removePo(detail)" class="flex-1 py-2 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 font-medium">Hapus</button>
        </div>
      </div>
    </div>

    <div v-if="toast" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
