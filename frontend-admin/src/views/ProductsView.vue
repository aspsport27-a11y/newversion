<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isAdminUnit = computed(() => auth.user?.role === 'admin_unit')
const isManager = computed(() => auth.user?.role === 'manager_unit')

const venues = ref([])
const venueId = ref(null)
const products = ref([])
const suppliers = ref([])
const categories = ref([])
const loading = ref(false)
const search = ref('')
const categoryFilter = ref('')
// kategori punya tabel global (bukan per-venue) — dropdown filter cuma tampilkan
// kategori yang benar2 dipakai produk di venue yg sedang dipilih, biar tak numpuk
// duplikat mirip dari venue lain (mis. "CAFE" vs "Café")
const availableCategories = computed(() => {
  const seen = new Map()
  for (const p of products.value) {
    if (p.category_id != null && !seen.has(p.category_id)) {
      seen.set(p.category_id, p.category_name || '—')
    }
  }
  return Array.from(seen, ([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name))
})
const filteredProducts = computed(() => {
  let list = products.value
  if (categoryFilter.value) {
    list = list.filter((p) => String(p.category_id || '') === String(categoryFilter.value))
  }
  const q = search.value.trim().toLowerCase()
  if (q) {
    list = list.filter((p) =>
      p.name.toLowerCase().includes(q) ||
      p.sku.toLowerCase().includes(q) ||
      (p.category_name || '').toLowerCase().includes(q) ||
      supName(p.supplier_id).toLowerCase().includes(q)
    )
  }
  return list
})

// ---- Paging ----
const page = ref(1)
const pageSize = ref(20)
const totalPages = computed(() => Math.max(1, Math.ceil(filteredProducts.value.length / pageSize.value)))
const pagedProducts = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredProducts.value.slice(start, start + pageSize.value)
})
watch([search, categoryFilter, pageSize], () => { page.value = 1 })
watch(totalPages, (tp) => { if (page.value > tp) page.value = tp })
function supName(id) { const s = suppliers.value.find((x) => x.id === id); return s ? s.name : '—' }
const showForm = ref(false)
const editing = ref(null)
const form = ref({})
const error = ref('')
const saving = ref(false)

// ---- Isi Ambang Stok (min_stock) massal ----
const showBulkMin = ref(false)
const bulkForm = ref({ min_stock: 10, allVenues: false, overwrite: false })
const bulkBusy = ref(false)
function openBulkMin() { bulkForm.value = { min_stock: 10, allVenues: false, overwrite: false }; showBulkMin.value = true }
async function applyBulkMin() {
  if (!bulkForm.value.min_stock || bulkForm.value.min_stock <= 0) { alert('Isi angka lebih dari 0'); return }
  bulkBusy.value = true
  try {
    const { data } = await client.post('/admin/products/bulk-min-stock', {
      venue_id: bulkForm.value.allVenues ? null : venueId.value,
      min_stock: bulkForm.value.min_stock,
      overwrite: bulkForm.value.overwrite,
    })
    showBulkMin.value = false
    await loadProducts()
    alert(`${data.updated} produk diperbarui.`)
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { bulkBusy.value = false }
}

function rupiah(n) {
  return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
}

function downloadProductTemplate() {
  const sample = suppliers.value[0]?.supplier_code || 'SUP-001'
  const rows = [
    ['name', 'price', 'unit', 'category', 'stock_qty', 'min_stock', 'track_stock', 'supplier_code'],
    ['Air Mineral 600ml', '5000', 'botol', 'Minuman', '50', '10', '1', sample],
  ]
  const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\r\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'template-produk.csv'; a.click()
  URL.revokeObjectURL(url)
}
const fileInput = ref(null)
const importing = ref(false)
function triggerImport() { fileInput.value?.click() }
async function onFile(e) {
  const file = e.target.files[0]
  e.target.value = ''
  if (!file || !venueId.value) return
  importing.value = true
  try {
    const fd = new FormData(); fd.append('file', file)
    const { data } = await client.post(`/admin/products/import?venue_id=${venueId.value}`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    await loadProducts()
    let msg = `${data.created} produk berhasil diimpor.`
    if (data.skipped?.length) msg += `\nDilewati ${data.skipped.length} baris:\n` + data.skipped.map((s) => `- Baris ${s.row}: ${s.reason}`).join('\n')
    alert(msg)
  } catch (e) { alert(e?.response?.data?.message || 'Gagal mengimpor CSV.') } finally { importing.value = false }
}

async function loadVenues() {
  const { data } = await client.get('/venues')
  venues.value = data.venues
  // manager_unit dibatasi ke venue-nya sendiri; admin_unit hanya venue di areanya
  if (isManager.value) venues.value = venues.value.filter((x) => x.id === auth.user?.venue_id)
  else if (isAdminUnit.value) venues.value = venues.value.filter((x) => x.area_id === auth.user?.area_id)
  if (venues.value.length && !venueId.value) venueId.value = venues.value[0].id
  try { suppliers.value = (await client.get('/procurement/suppliers')).data.suppliers } catch { /* ignore */ }
  try { categories.value = (await client.get('/admin/product-categories')).data.categories } catch { /* ignore */ }
}
async function loadProducts() {
  if (!venueId.value) return
  loading.value = true
  try {
    const { data } = await client.get('/admin/products', { params: { venue_id: venueId.value, ticket: 0 } })
    products.value = data.products
  } finally {
    loading.value = false
  }
}
onMounted(async () => {
  await loadVenues()
  await loadProducts()
})
watch(venueId, () => { search.value = ''; categoryFilter.value = ''; page.value = 1; loadProducts() })

function openCreate() {
  editing.value = null
  form.value = { name: '', price: 0, unit: 'pcs', stock_qty: 0, min_stock: 0, track_stock: true, category: '', supplier_id: '', is_consignment: false, consignment_price: null }
  error.value = ''
  showForm.value = true
}
function openEdit(p) {
  editing.value = p
  form.value = { name: p.name, price: p.price, stock_qty: p.stock_qty, min_stock: p.min_stock, track_stock: p.track_stock, supplier_id: p.supplier_id || '', category: p.category_name || '', is_consignment: p.is_consignment || false, consignment_price: p.consignment_price, is_active: p.is_active }
  error.value = ''
  showForm.value = true
}
async function removeProduct(p) {
  if (!window.confirm(`Hapus produk "${p.name}"?`)) return
  try {
    await client.delete(`/admin/products/${p.id}`)
    await loadProducts()
  } catch (e) {
    alert(e?.response?.data?.message || 'Gagal menghapus.')
  }
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
        <p class="text-slate-500 mt-1">Kelola produk F&amp;B per venue. (Tiket dikelola di menu Lapangan &amp; Tiket.)</p>
      </div>
      <div class="flex flex-wrap gap-2 items-center">
        <select v-if="!isManager" v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select>
        <button @click="downloadProductTemplate" class="text-brand-600 hover:underline text-sm px-2 py-2">📥 Unduh Template CSV</button>
        <input ref="fileInput" type="file" accept=".csv" class="hidden" @change="onFile" />
        <button @click="triggerImport" :disabled="importing" class="bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">{{ importing ? 'Mengimpor…' : '📤 Upload CSV' }}</button>
        <button @click="openBulkMin" class="bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm rounded-lg px-4 py-2 font-medium">⚙️ Isi Ambang Stok</button>
        <button @click="openCreate" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Produk</button>
      </div>
    </div>

    <div class="mb-3 flex flex-wrap gap-2">
      <input v-model="search" type="text" placeholder="🔍 Cari nama, SKU, atau supplier…"
        class="w-full max-w-sm rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
      <select v-model="categoryFilter" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
        <option value="">Semua kategori</option>
        <option v-for="c in availableCategories" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th class="px-4 py-3 font-medium">SKU</th>
              <th class="px-4 py-3 font-medium">Nama</th>
              <th class="px-4 py-3 font-medium">Kategori</th>
              <th class="px-4 py-3 font-medium">Supplier</th>
              <th class="px-4 py-3 font-medium text-right">Harga</th>
              <th class="px-4 py-3 font-medium text-right">Stok</th>
              <th class="px-4 py-3 font-medium text-center">Status</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading"><td colspan="8" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!products.length"><td colspan="8" class="px-4 py-8 text-center text-slate-400">Belum ada produk.</td></tr>
            <tr v-else-if="!filteredProducts.length"><td colspan="8" class="px-4 py-8 text-center text-slate-400">Tidak ada produk yang cocok dengan pencarian.</td></tr>
            <tr v-for="p in pagedProducts" :key="p.id" class="border-t hover:bg-slate-50">
              <td class="px-4 py-3 font-mono text-slate-500">{{ p.sku }}</td>
              <td class="px-4 py-3 font-medium text-slate-700">
                {{ p.name }}
                <span v-if="p.is_consignment" class="ml-1 text-[10px] bg-amber-100 text-amber-700 rounded px-1.5 py-0.5">Konsinyasi</span>
              </td>
              <td class="px-4 py-3 text-slate-500">{{ p.category_name || '—' }}</td>
              <td class="px-4 py-3 text-slate-500">{{ supName(p.supplier_id) }}</td>
              <td class="px-4 py-3 text-right">
                <template v-if="p.promo && p.effective_price < p.price">
                  <span class="text-emerald-600 font-medium">{{ rupiah(p.effective_price) }}</span>
                  <span class="text-xs text-slate-400 line-through ml-1">{{ rupiah(p.price) }}</span>
                </template>
                <span v-else>{{ rupiah(p.price) }}</span>
                <div v-if="p.promo" class="text-[10px] text-amber-600">🎉 {{ p.promo.label }}</div>
              </td>
              <td class="px-4 py-3 text-right">{{ p.track_stock ? p.stock_qty : '—' }}</td>
              <td class="px-4 py-3 text-center">
                <span :class="p.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="text-xs rounded-full px-2 py-0.5">
                  {{ p.is_active ? 'Aktif' : 'Nonaktif' }}
                </span>
              </td>
              <td class="px-4 py-3 text-right whitespace-nowrap">
                <button @click="openEdit(p)" class="text-brand-600 text-sm hover:underline mr-3">Edit</button>
                <button @click="removeProduct(p)" class="text-red-500 text-sm hover:underline">Hapus</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="filteredProducts.length" class="flex items-center justify-between gap-3 px-4 py-3 border-t flex-wrap">
        <p class="text-xs text-slate-500">
          Menampilkan {{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, filteredProducts.length) }} dari {{ filteredProducts.length }} produk
        </p>
        <div class="flex items-center gap-2">
          <select v-model.number="pageSize" class="rounded-lg border border-slate-300 px-2 py-1.5 text-xs outline-none focus:border-brand-500">
            <option :value="10">10 / halaman</option>
            <option :value="20">20 / halaman</option>
            <option :value="50">50 / halaman</option>
            <option :value="100">100 / halaman</option>
          </select>
          <button @click="page = 1" :disabled="page === 1" class="text-xs px-2 py-1.5 rounded-lg border border-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50">«</button>
          <button @click="page--" :disabled="page === 1" class="text-xs px-2 py-1.5 rounded-lg border border-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50">‹ Sebelumnya</button>
          <span class="text-xs text-slate-500">Halaman {{ page }} / {{ totalPages }}</span>
          <button @click="page++" :disabled="page === totalPages" class="text-xs px-2 py-1.5 rounded-lg border border-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50">Berikutnya ›</button>
          <button @click="page = totalPages" :disabled="page === totalPages" class="text-xs px-2 py-1.5 rounded-lg border border-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50">»</button>
        </div>
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
          <p v-if="!editing" class="text-xs text-slate-400">SKU dibuat otomatis (mis. {{ venues.find(v=>v.id===venueId)?.code }}-001).</p>
          <input v-model="form.name" placeholder="Nama produk" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <div>
            <label class="block text-xs text-slate-500 mb-1">Kategori</label>
            <input v-model="form.category" list="category-options" placeholder="mis. Minuman (pilih atau ketik baru)"
              class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
            <datalist id="category-options">
              <option v-for="c in categories" :key="c.id" :value="c.name" />
            </datalist>
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Supplier (default utk PO)</label>
            <select v-model="form.supplier_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option value="">— tanpa supplier —</option>
              <option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>
          <div class="bg-amber-50 rounded-lg p-3">
            <label class="flex items-center gap-2 text-sm text-slate-700 font-medium">
              <input v-model="form.is_consignment" type="checkbox" /> Produk Konsinyasi (titip barang)
            </label>
            <div v-if="form.is_consignment" class="mt-2">
              <label class="block text-xs text-slate-500 mb-1">Harga Bagi Hasil ke Supplier (per unit terjual)</label>
              <input v-model.number="form.consignment_price" type="number" placeholder="mis. 3000"
                class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
              <p class="text-xs text-slate-400 mt-1">Bukan persentase — jumlah tetap Rp yg dibayar ke supplier tiap 1 unit terjual. Selisih dgn harga jual jadi margin venue. Dihitung di menu Procurement → tab Konsinyasi.</p>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-xs text-slate-500 mb-1">Harga</label>
              <input v-model.number="form.price" type="number" placeholder="Harga" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
            </div>
            <div>
              <label class="block text-xs text-slate-500 mb-1">Stok</label>
              <input v-model.number="form.stock_qty" type="number" placeholder="Stok" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
            </div>
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Min. stok (alert reorder)</label>
            <input v-model.number="form.min_stock" type="number" placeholder="0 = tak ada alert" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <p class="text-xs text-slate-400">Promo diatur di menu <span class="font-medium text-slate-500">Promo</span>.</p>
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

    <!-- Modal Isi Ambang Stok Massal -->
    <div v-if="showBulkMin" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="showBulkMin = false">
      <div class="bg-white w-full max-w-sm rounded-2xl p-5">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-slate-800">Isi Ambang Stok Otomatis</h3>
          <button @click="showBulkMin = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <p class="text-xs text-slate-400 mb-3">Supaya produk muncul di "Stok Menipis" (Procurement) sebelum benar-benar habis. Nilai ini jadi ambang minimum — di bawahnya dianggap perlu di-reorder.</p>
        <div class="space-y-3">
          <div>
            <label class="block text-xs text-slate-500 mb-1">Ambang stok minimum</label>
            <input v-model.number="bulkForm.min_stock" type="number" min="1" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <label class="flex items-center gap-2 text-sm text-slate-600">
            <input v-model="bulkForm.allVenues" type="checkbox" /> Terapkan ke semua venue (bukan cuma {{ venues.find(v=>v.id===venueId)?.code }})
          </label>
          <label class="flex items-center gap-2 text-sm text-slate-600">
            <input v-model="bulkForm.overwrite" type="checkbox" /> Timpa nilai yang sudah diatur sebelumnya
          </label>
          <p class="text-xs text-slate-400">{{ bulkForm.overwrite ? 'Semua produk aktif (lacak stok) akan diubah.' : 'Hanya produk yang ambang stoknya masih 0/belum diatur.' }}</p>
          <button @click="applyBulkMin" :disabled="bulkBusy" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">
            {{ bulkBusy ? 'Menerapkan…' : 'Terapkan' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
