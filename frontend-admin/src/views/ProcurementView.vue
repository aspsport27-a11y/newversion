<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isManager = computed(() => auth.user?.role === 'manager_unit')
const isAdminUnit = computed(() => auth.user?.role === 'admin_unit')
const isApprover = computed(() => ['admin', 'head_office'].includes(auth.user?.role))
const canSupplier = computed(() => auth.hasPerm('proc.supplier'))  // kelola supplier

const tab = ref('po')
const venues = ref([])
const venueId = ref('')
const suppliers = ref([])
const products = ref([])
const toast = ref('')

function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2500) }
function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }

function downloadCsv(filename, rows) {
  const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\r\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}
function downloadSupplierTemplate() {
  downloadCsv('template-supplier.csv', [
    ['name', 'contact_person', 'phone', 'email', 'address', 'city', 'payment_terms', 'bank_account'],
    ['CV Contoh Supplier', 'Pak Budi', '081234567890', 'budi@email.com', 'Jl. Contoh No.1', 'Banjarmasin', 'NET 30', 'BCA 1234567890'],
  ])
}
const supFileInput = ref(null)
const importingSup = ref(false)
function triggerSupImport() { supFileInput.value?.click() }
async function onSupFile(e) {
  const file = e.target.files[0]
  e.target.value = ''
  if (!file) return
  importingSup.value = true
  try {
    const fd = new FormData(); fd.append('file', file)
    const { data } = await client.post('/procurement/suppliers/import', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    await loadBase()
    let msg = `${data.created} supplier berhasil diimpor.`
    if (data.skipped?.length) msg += `\nDilewati ${data.skipped.length} baris:\n` + data.skipped.map((s) => `- Baris ${s.row}: ${s.reason}`).join('\n')
    alert(msg)
  } catch (e) { alert(e?.response?.data?.message || 'Gagal mengimpor CSV.') } finally { importingSup.value = false }
}
const statusMap = { submitted: ['Menunggu', 'bg-amber-100 text-amber-700'], approved: ['Disetujui', 'bg-blue-100 text-blue-700'], received: ['Diterima', 'bg-violet-100 text-violet-700'], paid: ['Lunas', 'bg-emerald-100 text-emerald-700'], rejected: ['Ditolak', 'bg-red-100 text-red-600'] }
function supName(id) { const s = suppliers.value.find((x) => x.id === id); return s ? s.name : '—' }

const accounts = ref([])
const sourceAccount = ref('')
async function loadBase() {
  const [v, s] = await Promise.all([client.get('/venues'), client.get('/procurement/suppliers')])
  venues.value = v.data.venues
  // admin_unit hanya venue di areanya
  if (isAdminUnit.value) venues.value = venues.value.filter((x) => x.area_id === auth.user?.area_id)
  suppliers.value = s.data.suppliers
  // default: "Semua venue" (venueId tetap '') agar semua PO tampil sekaligus
  if (isApprover.value) {
    try {
      const { data } = await client.get('/treasury/accounts')
      accounts.value = data.accounts
      sourceAccount.value = data.accounts.find((a) => a.type === 'holding')?.id || data.accounts[0]?.id || ''
    } catch (_) { /* treasury belum disetup */ }
  }
}
async function loadProducts(vid) {
  const params = {}
  if (!isManager.value && vid) params.venue_id = vid
  const { data } = await client.get('/procurement/products', { params })
  products.value = data.products
}

// -------- PO --------
const pos = ref([])
const loadingPo = ref(false)
async function loadPo() {
  loadingPo.value = true
  const params = {}
  if (!isManager.value && venueId.value) params.venue_id = venueId.value
  try { const { data } = await client.get('/procurement/pos', { params }); pos.value = data.pos }
  finally { loadingPo.value = false }
}
const showCreate = ref(false)
const cForm = ref({ supplier_id: '', notes: '', items: [] })
const cFiles = ref([])
const cErr = ref('')
const saving = ref(false)
const cTotal = computed(() => cForm.value.items.reduce((s, i) => s + (Number(i.quantity) || 0) * (Number(i.unit_price) || 0), 0))
async function openCreate() {
  const vid = venueId.value || venues.value[0]?.id
  try { await loadProducts(vid) } catch (e) { products.value = [] }  // tetap buka modal walau produk gagal (bisa item non-stok)
  cForm.value = { venue_id: vid, supplier_id: suppliers.value[0]?.id || '', notes: '', items: [{ mode: 'product', product_id: products.value[0]?.id, item_name: '', quantity: 1, unit: 'pcs', unit_price: null, note: '' }] }
  cFiles.value = []; cErr.value = ''; showCreate.value = true
}
async function onModalVenueChange() {
  try { await loadProducts(cForm.value.venue_id) } catch (e) { products.value = [] }
  cForm.value.items = [{ mode: 'product', product_id: products.value[0]?.id, item_name: '', quantity: 1, unit: 'pcs', unit_price: null, note: '' }]
}
function addRow() { cForm.value.items.push({ mode: 'product', product_id: products.value[0]?.id, item_name: '', quantity: 1, unit: 'pcs', unit_price: null, note: '' }) }
// saat pilih produk → auto isi supplier PO dari supplier default produk
function onPickProduct(it) {
  const p = products.value.find((x) => x.id === it.product_id)
  if (p?.supplier_id) cForm.value.supplier_id = p.supplier_id
}
function rmRow(i) { cForm.value.items.splice(i, 1) }
function onFiles(e) { cFiles.value = Array.from(e.target.files) }
async function submitCreate() {
  saving.value = true; cErr.value = ''
  try {
    const items = cForm.value.items.map((i) => i.mode === 'product'
      ? { product_id: i.product_id, quantity: i.quantity, unit: i.unit, unit_price: i.unit_price, note: i.note }
      : { item_name: i.item_name, quantity: i.quantity, unit: i.unit, unit_price: i.unit_price, note: i.note })
    const payload = { supplier_id: cForm.value.supplier_id || null, notes: cForm.value.notes, items }
    if (!isManager.value) payload.venue_id = cForm.value.venue_id
    const { data } = await client.post('/procurement/pos', payload)
    for (const f of cFiles.value) { const fd = new FormData(); fd.append('file', f); await client.post(`/procurement/pos/${data.po.id}/attachment`, fd, { headers: { 'Content-Type': 'multipart/form-data' } }) }
    showCreate.value = false; await loadPo(); flash('PO dibuat')
  } catch (e) { cErr.value = e?.response?.data?.message || 'Gagal.' } finally { saving.value = false }
}

const detail = ref(null)
const busy = ref(false)
async function openDetail(p) { const { data } = await client.get(`/procurement/pos/${p.id}`); detail.value = data.po }
async function act(action, extra = {}) {
  busy.value = true
  try { await client.post(`/procurement/pos/${detail.value.id}/${action}`, extra); const { data } = await client.get(`/procurement/pos/${detail.value.id}`); detail.value = data.po; await loadPo(); flash('Berhasil') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
function doReject() { const reason = prompt('Alasan penolakan:'); if (reason !== null) act('reject', { reason }) }
async function viewAtt(a) { const res = await client.get(`/procurement/attachments/${a.id}`, { responseType: 'blob' }); window.open(URL.createObjectURL(res.data), '_blank') }

// -------- Supplier --------
const showSup = ref(false)
const supForm = ref({})
const editingSup = ref(null)
async function openSupCreate() { editingSup.value = null; supForm.value = { name: '', contact_person: '', phone: '', bank_account: '', payment_terms: '', city: '' }; showSup.value = true }
function openSupEdit(s) { editingSup.value = s; supForm.value = { ...s }; showSup.value = true }
async function saveSup() {
  try {
    if (editingSup.value) await client.put(`/procurement/suppliers/${editingSup.value.id}`, supForm.value)
    else await client.post('/procurement/suppliers', supForm.value)
    showSup.value = false; await loadBase(); flash('Supplier disimpan')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') }
}
async function removeSup(s) { if (!window.confirm(`Hapus supplier ${s.name}?`)) return; try { await client.delete(`/procurement/suppliers/${s.id}`); await loadBase(); flash('Dihapus') } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } }

// -------- Reorder --------
const reorder = ref([])
async function loadReorder() {
  const params = {}
  if (!isManager.value && venueId.value) params.venue_id = venueId.value
  const { data } = await client.get('/procurement/reorder', { params }); reorder.value = data.products
}

function reloadTab() { tab.value === 'po' ? loadPo() : tab.value === 'reorder' ? loadReorder() : null }
onMounted(async () => { await loadBase(); await loadPo() })
watch([venueId], reloadTab)
watch(tab, reloadTab)
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-5">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">Procurement</h1>
        <p class="text-slate-500 mt-1">Purchase order, supplier, dan stok menipis.</p>
      </div>
      <select v-if="!isManager" v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
        <option value="">Semua venue</option>
        <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
      </select>
    </div>

    <div class="flex gap-1 mb-4 border-b">
      <button @click="tab = 'po'" :class="tab === 'po' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Purchase Order</button>
      <button @click="tab = 'reorder'" :class="tab === 'reorder' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Stok Menipis</button>
      <button @click="tab = 'supplier'" :class="tab === 'supplier' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Supplier</button>
    </div>

    <!-- ===== PO ===== -->
    <div v-if="tab === 'po'">
      <div class="flex justify-end mb-3"><button @click="openCreate" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Buat PO</button></div>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-4 py-3 font-medium">Kode</th>
              <th v-if="!isManager" class="px-4 py-3 font-medium">Venue</th>
              <th class="px-4 py-3 font-medium">Supplier</th>
              <th class="px-4 py-3 font-medium text-right">Total</th><th class="px-4 py-3 font-medium text-center">Status</th><th class="px-4 py-3"></th>
            </tr></thead>
            <tbody>
              <tr v-if="loadingPo"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
              <tr v-else-if="!pos.length"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Belum ada PO.</td></tr>
              <tr v-for="p in pos" :key="p.id" @click="openDetail(p)" class="border-t hover:bg-slate-50 cursor-pointer">
                <td class="px-4 py-3 font-mono text-xs text-slate-500">{{ p.code }}</td>
                <td v-if="!isManager" class="px-4 py-3 text-slate-600">{{ venues.find(v=>v.id===p.venue_id)?.code || '—' }}</td>
                <td class="px-4 py-3 text-slate-600">{{ p.supplier_name || '—' }}</td>
                <td class="px-4 py-3 text-right font-medium">{{ rupiah(p.total_amount) }}</td>
                <td class="px-4 py-3 text-center"><span :class="statusMap[p.status]?.[1]" class="text-xs rounded-full px-2 py-0.5">{{ statusMap[p.status]?.[0] }}</span></td>
                <td class="px-4 py-3 text-right text-brand-600 text-sm">Detail</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ===== Reorder ===== -->
    <div v-else-if="tab === 'reorder'">
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-3 font-medium">Produk</th>
            <th v-if="!isManager" class="px-4 py-3 font-medium">Venue</th>
            <th class="px-4 py-3 font-medium text-right">Stok</th><th class="px-4 py-3 font-medium text-right">Min</th><th class="px-4 py-3 font-medium text-right">Kurang</th>
          </tr></thead>
          <tbody>
            <tr v-if="!reorder.length"><td colspan="5" class="px-4 py-8 text-center text-emerald-600">Semua stok aman 🎉</td></tr>
            <tr v-for="p in reorder" :key="p.id" class="border-t">
              <td class="px-4 py-3 font-medium text-slate-700">{{ p.name }}</td>
              <td v-if="!isManager" class="px-4 py-3 text-slate-500">{{ venues.find(v=>v.id===p.venue_id)?.code || '—' }}</td>
              <td class="px-4 py-3 text-right text-red-600 font-medium">{{ p.stock_qty }}</td>
              <td class="px-4 py-3 text-right text-slate-500">{{ p.min_stock }}</td>
              <td class="px-4 py-3 text-right text-amber-600">{{ Math.max(0, p.min_stock - p.stock_qty) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ===== Supplier ===== -->
    <div v-else>
      <div v-if="canSupplier" class="flex justify-end items-center gap-2 mb-3">
        <button @click="downloadSupplierTemplate" class="text-brand-600 hover:underline text-sm px-2 py-2">📥 Unduh Template CSV</button>
        <input ref="supFileInput" type="file" accept=".csv" class="hidden" @change="onSupFile" />
        <button @click="triggerSupImport" :disabled="importingSup" class="bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">{{ importingSup ? 'Mengimpor…' : '📤 Upload CSV' }}</button>
        <button @click="openSupCreate" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Supplier</button>
      </div>
      <p v-else class="text-xs text-slate-400 mb-3">Hanya lihat — tidak punya izin kelola supplier.</p>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-3 font-medium">Kode</th><th class="px-4 py-3 font-medium">Nama</th><th class="px-4 py-3 font-medium">Kontak</th><th class="px-4 py-3 font-medium">No. Rekening</th><th class="px-4 py-3"></th>
          </tr></thead>
          <tbody>
            <tr v-if="!suppliers.length"><td colspan="5" class="px-4 py-8 text-center text-slate-400">Belum ada supplier.</td></tr>
            <tr v-for="s in suppliers" :key="s.id" class="border-t hover:bg-slate-50">
              <td class="px-4 py-3 font-mono text-slate-500">{{ s.supplier_code }}</td>
              <td class="px-4 py-3 font-medium text-slate-700">{{ s.name }}</td>
              <td class="px-4 py-3 text-slate-600">{{ s.contact_person || '—' }} {{ s.phone ? '· ' + s.phone : '' }}</td>
              <td class="px-4 py-3 text-slate-500">{{ s.bank_account || '—' }}</td>
              <td class="px-4 py-3 text-right whitespace-nowrap"><template v-if="canSupplier"><button @click="openSupEdit(s)" class="text-brand-600 text-sm hover:underline">Edit</button><button @click="removeSup(s)" class="text-red-500 text-sm hover:underline ml-3">Hapus</button></template><span v-else class="text-slate-300 text-xs">—</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Create PO modal -->
    <div v-if="showCreate" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-2xl rounded-2xl p-5 max-h-[92vh] overflow-auto">
        <div class="flex justify-between items-center mb-4"><h3 class="text-lg font-bold text-slate-800">Buat Purchase Order</h3><button @click="showCreate = false" class="text-slate-400 text-xl">✕</button></div>
        <div class="grid grid-cols-2 gap-3 mb-3">
          <div v-if="!isManager"><label class="block text-xs text-slate-500 mb-1">Venue</label>
            <select v-model="cForm.venue_id" @change="onModalVenueChange" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
            </select></div>
          <div><label class="block text-xs text-slate-500 mb-1">Supplier</label>
            <select v-model="cForm.supplier_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option value="">— pilih —</option><option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select></div>
          <div class="col-span-2"><label class="block text-xs text-slate-500 mb-1">Catatan</label><input v-model="cForm.notes" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
        </div>
        <p class="text-xs font-medium text-slate-500 mb-1">Item</p>
        <div v-for="(it, i) in cForm.items" :key="i" class="border rounded-lg p-2 mb-2">
          <div class="flex gap-2 mb-2">
            <select v-model="it.mode" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm w-28">
              <option value="product">Produk</option><option value="other">Non-stok</option>
            </select>
            <select v-if="it.mode === 'product'" v-model="it.product_id" @change="onPickProduct(it)" class="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
              <option v-for="p in products" :key="p.id" :value="p.id">{{ p.name }} (stok {{ p.stock_qty }})</option>
            </select>
            <input v-else v-model="it.item_name" placeholder="Nama barang (non-stok)" class="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm" />
            <button @click="rmRow(i)" class="text-red-400 px-1">✕</button>
          </div>
          <div class="grid grid-cols-3 gap-2">
            <input v-model.number="it.quantity" type="number" placeholder="Qty" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm" />
            <input v-model="it.unit" placeholder="Satuan" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm" />
            <input v-model.number="it.unit_price" type="number" placeholder="Harga/unit" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm text-right" />
          </div>
        </div>
        <button @click="addRow" class="text-brand-600 text-sm mb-3">+ item</button>
        <div class="flex justify-between font-semibold mb-3"><span>Total</span><span class="text-brand-700">{{ rupiah(cTotal) }}</span></div>
        <label class="block text-xs text-slate-500 mb-1">Bukti/nota (foto/PDF)</label>
        <input type="file" multiple accept="image/*,.pdf" @change="onFiles" class="w-full text-sm mb-3" />
        <p v-if="cErr" class="text-sm text-red-600 mb-2">{{ cErr }}</p>
        <button @click="submitCreate" :disabled="saving || !cTotal" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">{{ saving ? 'Menyimpan…' : 'Buat PO' }}</button>
      </div>
    </div>

    <!-- Detail PO modal -->
    <div v-if="detail" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="detail = null">
      <div class="bg-white w-full max-w-lg rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-start mb-3">
          <div><h3 class="text-lg font-bold text-slate-800">{{ detail.code }}</h3><p class="text-sm text-slate-500">{{ detail.supplier_name || 'Tanpa supplier' }}</p></div>
          <span :class="statusMap[detail.status]?.[1]" class="text-xs rounded-full px-2 py-1">{{ statusMap[detail.status]?.[0] }}</span>
        </div>
        <p v-if="detail.notes" class="text-sm text-slate-600 mb-3">{{ detail.notes }}</p>
        <div class="border rounded-lg overflow-hidden mb-3">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left text-xs"><tr><th class="px-3 py-2">Item</th><th class="px-3 py-2 text-right">Qty</th><th class="px-3 py-2 text-right">Subtotal</th></tr></thead>
            <tbody>
              <tr v-for="it in detail.items" :key="it.id" class="border-t">
                <td class="px-3 py-2 text-slate-700">{{ it.item_name }} <span v-if="it.is_stock" class="text-[10px] bg-emerald-100 text-emerald-700 rounded px-1">stok</span></td>
                <td class="px-3 py-2 text-right">{{ it.quantity }} {{ it.unit }}</td>
                <td class="px-3 py-2 text-right">{{ rupiah(it.total_price) }}</td>
              </tr>
            </tbody>
            <tfoot><tr class="border-t bg-slate-50 font-semibold"><td class="px-3 py-2" colspan="2">Total</td><td class="px-3 py-2 text-right">{{ rupiah(detail.total_amount) }}</td></tr></tfoot>
          </table>
        </div>
        <div v-if="detail.rejection_reason" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">Ditolak: {{ detail.rejection_reason }}</div>
        <div class="mb-3">
          <p class="text-xs font-medium text-slate-500 mb-1">Bukti</p>
          <div v-if="!detail.attachments.length" class="text-sm text-slate-400">Tidak ada lampiran.</div>
          <div v-else class="flex flex-wrap gap-2"><button v-for="a in detail.attachments" :key="a.id" @click="viewAtt(a)" class="text-xs bg-slate-100 hover:bg-slate-200 text-slate-600 rounded px-2 py-1">📎 {{ a.filename }}</button></div>
        </div>
        <div class="flex gap-2 pt-2 border-t">
          <template v-if="detail.status === 'submitted'">
            <button @click="act('approve')" :disabled="busy" class="flex-1 py-2.5 rounded-lg bg-emerald-600 text-white font-medium disabled:opacity-50">Setujui</button>
            <button @click="doReject" :disabled="busy" class="flex-1 py-2.5 rounded-lg bg-red-600 text-white font-medium disabled:opacity-50">Tolak</button>
          </template>
          <button v-else-if="detail.status === 'approved'" @click="act('receive')" :disabled="busy" class="w-full py-2.5 rounded-lg bg-violet-600 text-white font-medium disabled:opacity-50">Barang Diterima (stok masuk)</button>
          <template v-else-if="detail.status === 'received' && isApprover">
            <div class="w-full">
              <label class="block text-xs text-slate-500 mb-1">Sumber dana</label>
              <select v-model="sourceAccount" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500 mb-2">
                <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }} ({{ rupiah(a.balance) }})</option>
              </select>
              <button @click="act('pay', { source_account_id: sourceAccount })" :disabled="busy" class="w-full py-2.5 rounded-lg bg-brand-600 text-white font-medium disabled:opacity-50">Bayar Supplier</button>
            </div>
          </template>
          <p v-else class="text-sm text-slate-400 py-2 text-center w-full">Status: {{ statusMap[detail.status]?.[0] }}<span v-if="detail.status === 'received'"> — menunggu pembayaran HO</span></p>
        </div>
      </div>
    </div>

    <!-- Supplier modal -->
    <div v-if="showSup" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-md rounded-2xl p-5">
        <div class="flex justify-between items-center mb-4"><h3 class="text-lg font-bold text-slate-800">{{ editingSup ? 'Edit' : 'Supplier Baru' }}</h3><button @click="showSup = false" class="text-slate-400 text-xl">✕</button></div>
        <div class="space-y-2">
          <input v-model="supForm.name" placeholder="Nama supplier" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <div class="grid grid-cols-2 gap-2">
            <input v-model="supForm.contact_person" placeholder="Kontak" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
            <input v-model="supForm.phone" placeholder="Telepon" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <input v-model="supForm.bank_account" placeholder="Rekening bank" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <input v-model="supForm.payment_terms" placeholder="Termin bayar (mis. NET 30)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <button @click="saveSup" class="w-full mt-2 py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium">Simpan</button>
        </div>
      </div>
    </div>

    <div v-if="toast" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
