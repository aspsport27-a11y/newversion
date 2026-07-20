<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isAdminUnit = computed(() => auth.user?.role === 'admin_unit')

const venues = ref([])
const venueId = ref(null)
const products = ref([])
const promos = ref([])
const loading = ref(false)
const showForm = ref(false)
const editing = ref(null)
const form = ref({})
const error = ref('')
const saving = ref(false)
const toast = ref('')

function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2500) }
function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function productName(id) { const p = products.value.find((x) => x.id === id); return p ? p.name : '—' }

const typeLabel = { price: 'Harga promo', percent: 'Diskon %', bogo: 'Beli X Gratis Y' }
function detail(p) {
  if (p.type === 'price') return rupiah(p.promo_price)
  if (p.type === 'percent') return p.percent + '%'
  if (p.type === 'bogo') return `Beli ${p.buy_qty} gratis ${p.get_qty}`
  return '—'
}
function period(p) {
  if (!p.start_date && !p.end_date) return 'Selalu'
  return `${p.start_date || '…'} → ${p.end_date || '…'}`
}

async function loadVenues() {
  const { data } = await client.get('/venues')
  venues.value = data.venues
  // admin_unit hanya venue di areanya
  if (isAdminUnit.value) venues.value = venues.value.filter((x) => x.area_id === auth.user?.area_id)
  if (venues.value.length && !venueId.value) venueId.value = venues.value[0].id
}
async function loadData() {
  if (!venueId.value) return
  loading.value = true
  try {
    const [pr, pm] = await Promise.all([
      client.get('/admin/products', { params: { venue_id: venueId.value } }),
      client.get('/admin/promos', { params: { venue_id: venueId.value } }),
    ])
    products.value = pr.data.products
    promos.value = pm.data.promos
  } finally { loading.value = false }
}
onMounted(async () => { await loadVenues(); await loadData() })
watch(venueId, loadData)

function openCreate() {
  editing.value = null
  form.value = { name: '', product_id: products.value[0]?.id, type: 'price', promo_price: null, percent: null, buy_qty: 2, get_qty: 1, start_date: '', end_date: '', is_active: true }
  error.value = ''; showForm.value = true
}
function openEdit(p) {
  editing.value = p
  form.value = { ...p, start_date: p.start_date || '', end_date: p.end_date || '' }
  error.value = ''; showForm.value = true
}
async function save() {
  saving.value = true; error.value = ''
  try {
    const payload = { ...form.value, start_date: form.value.start_date || null, end_date: form.value.end_date || null }
    if (editing.value) await client.put(`/admin/promos/${editing.value.id}`, payload)
    else await client.post('/admin/promos', payload)
    showForm.value = false
    await loadData()
    flash(editing.value ? 'Promo diperbarui' : 'Promo dibuat')
  } catch (e) {
    error.value = e?.response?.data?.message || 'Gagal menyimpan.'
  } finally { saving.value = false }
}
async function remove(p) {
  if (!window.confirm(`Hapus promo "${p.name}"?`)) return
  try { await client.delete(`/admin/promos/${p.id}`); await loadData(); flash('Promo dihapus') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal.') }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-6">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">Promo</h1>
        <p class="text-slate-500 mt-1">Diskon %, harga promo, beli-X-gratis-Y — dengan periode tanggal.</p>
      </div>
      <div class="flex gap-2">
        <select v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select>
        <button @click="openCreate" :disabled="!products.length" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">+ Promo</button>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th class="px-4 py-3 font-medium">Nama</th>
              <th class="px-4 py-3 font-medium">Produk</th>
              <th class="px-4 py-3 font-medium">Tipe</th>
              <th class="px-4 py-3 font-medium">Detail</th>
              <th class="px-4 py-3 font-medium">Periode</th>
              <th class="px-4 py-3 font-medium text-center">Status</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading"><td colspan="7" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!promos.length"><td colspan="7" class="px-4 py-8 text-center text-slate-400">Belum ada promo untuk venue ini.</td></tr>
            <tr v-for="p in promos" :key="p.id" class="border-t hover:bg-slate-50">
              <td class="px-4 py-3 font-medium text-slate-700">{{ p.name }}</td>
              <td class="px-4 py-3 text-slate-600">{{ p.product_name || productName(p.product_id) }}</td>
              <td class="px-4 py-3"><span class="text-xs bg-brand-50 text-brand-700 rounded px-2 py-0.5">{{ typeLabel[p.type] }}</span></td>
              <td class="px-4 py-3 text-slate-700">{{ detail(p) }}</td>
              <td class="px-4 py-3 text-slate-500 text-xs">{{ period(p) }}</td>
              <td class="px-4 py-3 text-center">
                <span :class="p.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="text-xs rounded-full px-2 py-0.5">{{ p.is_active ? 'Aktif' : 'Nonaktif' }}</span>
              </td>
              <td class="px-4 py-3 text-right whitespace-nowrap">
                <button @click="openEdit(p)" class="text-brand-600 text-sm hover:underline">Edit</button>
                <button @click="remove(p)" class="text-red-500 text-sm hover:underline ml-3">Hapus</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Form modal -->
    <div v-if="showForm" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-md rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-slate-800">{{ editing ? 'Edit Promo' : 'Promo Baru' }}</h3>
          <button @click="showForm = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <div class="space-y-3">
          <input v-model="form.name" placeholder="Nama promo (mis. Promo Akhir Pekan)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <div>
            <label class="block text-xs text-slate-500 mb-1">Produk</label>
            <select v-model="form.product_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option v-for="p in products" :key="p.id" :value="p.id">{{ p.name }} — {{ rupiah(p.price) }}</option>
            </select>
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Tipe promo</label>
            <select v-model="form.type" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option value="price">Harga promo (harga tetap)</option>
              <option value="percent">Diskon persen (%)</option>
              <option value="bogo">Beli X gratis Y</option>
            </select>
          </div>
          <input v-if="form.type === 'price'" v-model.number="form.promo_price" type="number" placeholder="Harga promo" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <input v-if="form.type === 'percent'" v-model.number="form.percent" type="number" placeholder="Diskon % (mis. 20)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <div v-if="form.type === 'bogo'" class="grid grid-cols-2 gap-2">
            <div><label class="block text-xs text-slate-500 mb-1">Beli (qty)</label><input v-model.number="form.buy_qty" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
            <div><label class="block text-xs text-slate-500 mb-1">Gratis (qty)</label><input v-model.number="form.get_qty" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div><label class="block text-xs text-slate-500 mb-1">Mulai (opsional)</label><input v-model="form.start_date" type="date" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
            <div><label class="block text-xs text-slate-500 mb-1">Selesai (opsional)</label><input v-model="form.end_date" type="date" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          </div>
          <label class="flex items-center gap-2 text-sm text-slate-600"><input v-model="form.is_active" type="checkbox" /> Aktif</label>
          <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
          <button @click="save" :disabled="saving" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">{{ saving ? 'Menyimpan…' : 'Simpan' }}</button>
        </div>
      </div>
    </div>

    <div v-if="toast" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
