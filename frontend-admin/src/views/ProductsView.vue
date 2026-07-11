<script setup>
import { ref, onMounted, watch } from 'vue'
import client from '../api/client'

const venues = ref([])
const venueId = ref(null)
const products = ref([])
const loading = ref(false)
const showForm = ref(false)
const editing = ref(null)
const form = ref({})
const error = ref('')
const saving = ref(false)

function rupiah(n) {
  return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
}

async function loadVenues() {
  const { data } = await client.get('/admin/venues')
  venues.value = data.venues
  if (venues.value.length && !venueId.value) venueId.value = venues.value[0].id
}
async function loadProducts() {
  if (!venueId.value) return
  loading.value = true
  try {
    const { data } = await client.get('/admin/products', { params: { venue_id: venueId.value } })
    products.value = data.products
  } finally {
    loading.value = false
  }
}
onMounted(async () => {
  await loadVenues()
  await loadProducts()
})
watch(venueId, loadProducts)

function openCreate() {
  editing.value = null
  form.value = { sku: '', name: '', price: 0, promo_price: null, unit: 'pcs', stock_qty: 0, track_stock: true, category: '' }
  error.value = ''
  showForm.value = true
}
function openEdit(p) {
  editing.value = p
  form.value = { name: p.name, price: p.price, promo_price: p.promo_price, stock_qty: p.stock_qty, track_stock: p.track_stock, is_active: p.is_active }
  error.value = ''
  showForm.value = true
}
async function save() {
  saving.value = true
  error.value = ''
  try {
    if (editing.value) {
      await client.put(`/admin/products/${editing.value.id}`, form.value)
    } else {
      await client.post('/admin/products', { ...form.value, venue_id: venueId.value })
    }
    showForm.value = false
    await loadProducts()
  } catch (e) {
    error.value = e?.response?.data?.message || 'Gagal menyimpan.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-6">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">Produk</h1>
        <p class="text-slate-500 mt-1">Kelola produk F&B, tiket, sewa alat per venue.</p>
      </div>
      <div class="flex gap-2">
        <select v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select>
        <button @click="openCreate" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Produk</button>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th class="px-4 py-3 font-medium">SKU</th>
              <th class="px-4 py-3 font-medium">Nama</th>
              <th class="px-4 py-3 font-medium text-right">Harga</th>
              <th class="px-4 py-3 font-medium text-right">Stok</th>
              <th class="px-4 py-3 font-medium text-center">Status</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!products.length"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Belum ada produk.</td></tr>
            <tr v-for="p in products" :key="p.id" class="border-t hover:bg-slate-50">
              <td class="px-4 py-3 font-mono text-slate-500">{{ p.sku }}</td>
              <td class="px-4 py-3 font-medium text-slate-700">{{ p.name }}</td>
              <td class="px-4 py-3 text-right">
                <template v-if="p.promo_price">
                  <span class="text-emerald-600 font-medium">{{ rupiah(p.effective_price) }}</span>
                  <span class="text-xs text-slate-400 line-through ml-1">{{ rupiah(p.price) }}</span>
                </template>
                <span v-else>{{ rupiah(p.price) }}</span>
              </td>
              <td class="px-4 py-3 text-right">{{ p.track_stock ? p.stock_qty : '—' }}</td>
              <td class="px-4 py-3 text-center">
                <span :class="p.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="text-xs rounded-full px-2 py-0.5">
                  {{ p.is_active ? 'Aktif' : 'Nonaktif' }}
                </span>
              </td>
              <td class="px-4 py-3 text-right">
                <button @click="openEdit(p)" class="text-brand-600 text-sm hover:underline">Edit</button>
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
          <h3 class="text-lg font-bold text-slate-800">{{ editing ? 'Edit Produk' : 'Produk Baru' }}</h3>
          <button @click="showForm = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <div class="space-y-3">
          <template v-if="!editing">
            <input v-model="form.sku" placeholder="SKU (mis. FB004)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
            <input v-model="form.category" placeholder="Kategori (mis. Minuman)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </template>
          <input v-model="form.name" placeholder="Nama produk" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-xs text-slate-500 mb-1">Harga normal</label>
              <input v-model.number="form.price" type="number" placeholder="Harga" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
            </div>
            <div>
              <label class="block text-xs text-slate-500 mb-1">Harga promo (opsional)</label>
              <input v-model.number="form.promo_price" type="number" placeholder="kosongkan bila tak ada" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
            </div>
          </div>
          <input v-model.number="form.stock_qty" type="number" placeholder="Stok" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <label class="flex items-center gap-2 text-sm text-slate-600">
            <input v-model="form.track_stock" type="checkbox" /> Lacak stok
          </label>
          <label v-if="editing" class="flex items-center gap-2 text-sm text-slate-600">
            <input v-model="form.is_active" type="checkbox" /> Aktif
          </label>
          <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
          <button @click="save" :disabled="saving" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">
            {{ saving ? 'Menyimpan…' : 'Simpan' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
