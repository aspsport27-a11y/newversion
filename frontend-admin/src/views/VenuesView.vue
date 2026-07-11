<script setup>
import { onMounted, ref, computed } from 'vue'
import client from '../api/client'

const venues = ref([])
const loading = ref(true)
const search = ref('')
const showForm = ref(false)
const editing = ref(null)
const form = ref({})
const error = ref('')
const saving = ref(false)
const toast = ref('')

function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2500) }
function rupiah(n) { return (Number(n) || 0).toLocaleString('id-ID') }

const filtered = computed(() => {
  const q = search.value.toLowerCase().trim()
  if (!q) return venues.value
  return venues.value.filter(
    (v) => v.name.toLowerCase().includes(q) || v.code.toLowerCase().includes(q) || (v.type || '').toLowerCase().includes(q),
  )
})

async function load() {
  loading.value = true
  try {
    const { data } = await client.get('/admin/venues')
    venues.value = data.venues
  } finally { loading.value = false }
}
onMounted(load)

function openCreate() {
  editing.value = null
  form.value = { code: '', name: '', type: '', city: '', capacity: null, address: '', phone: '', email: '' }
  error.value = ''; showForm.value = true
}
function openEdit(v) {
  editing.value = v
  form.value = { ...v }
  error.value = ''; showForm.value = true
}
async function save() {
  saving.value = true; error.value = ''
  try {
    if (editing.value) await client.put(`/admin/venues/${editing.value.id}`, form.value)
    else await client.post('/admin/venues', form.value)
    showForm.value = false
    await load()
    flash(editing.value ? 'Venue diperbarui' : 'Venue ditambahkan')
  } catch (e) {
    error.value = e?.response?.data?.message || 'Gagal menyimpan.'
  } finally { saving.value = false }
}
async function remove(v) {
  if (!window.confirm(`Hapus venue "${v.name}" (${v.code})?`)) return
  try {
    await client.delete(`/admin/venues/${v.id}`)
    await load()
    flash('Venue dihapus')
  } catch (e) {
    alert(e?.response?.data?.message || 'Gagal menghapus.')
  }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-6">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">Venue</h1>
        <p class="text-slate-500 mt-1">{{ venues.length }} unit venue terdaftar.</p>
      </div>
      <div class="flex gap-2">
        <input v-model="search" type="search" placeholder="Cari venue…"
          class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
        <button @click="openCreate" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium whitespace-nowrap">+ Venue</button>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th class="px-4 py-3 font-medium">Kode</th>
              <th class="px-4 py-3 font-medium">Nama</th>
              <th class="px-4 py-3 font-medium">Tipe</th>
              <th class="px-4 py-3 font-medium">Kota</th>
              <th class="px-4 py-3 font-medium text-right">Kapasitas</th>
              <th class="px-4 py-3 font-medium text-center">Status</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading"><td colspan="7" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!filtered.length"><td colspan="7" class="px-4 py-8 text-center text-slate-400">Tidak ada venue.</td></tr>
            <tr v-for="v in filtered" :key="v.id" class="border-t hover:bg-slate-50">
              <td class="px-4 py-3 font-mono text-slate-500">{{ v.code }}</td>
              <td class="px-4 py-3 font-medium text-slate-700">{{ v.name }}</td>
              <td class="px-4 py-3"><span class="text-xs bg-brand-50 text-brand-700 rounded px-2 py-0.5">{{ (v.type || '').replace(/_/g, ' ') }}</span></td>
              <td class="px-4 py-3 text-slate-600">{{ v.city || '—' }}</td>
              <td class="px-4 py-3 text-right text-slate-600">{{ rupiah(v.capacity) }}</td>
              <td class="px-4 py-3 text-center">
                <span :class="v.active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="text-xs rounded-full px-2 py-0.5">{{ v.active ? 'Aktif' : 'Nonaktif' }}</span>
              </td>
              <td class="px-4 py-3 text-right whitespace-nowrap">
                <button @click="openEdit(v)" class="text-brand-600 text-sm hover:underline">Edit</button>
                <button @click="remove(v)" class="text-red-500 text-sm hover:underline ml-3">Hapus</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Form modal -->
    <div v-if="showForm" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-lg rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-slate-800">{{ editing ? 'Edit Venue' : 'Venue Baru' }}</h3>
          <button @click="showForm = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-xs text-slate-500 mb-1">Kode *</label>
            <input v-model="form.code" placeholder="V013" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Tipe *</label>
            <input v-model="form.type" placeholder="futsal, padel…" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div class="col-span-2"><label class="block text-xs text-slate-500 mb-1">Nama *</label>
            <input v-model="form.name" placeholder="Nama venue" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Kota</label>
            <input v-model="form.city" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Kapasitas</label>
            <input v-model.number="form.capacity" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div class="col-span-2"><label class="block text-xs text-slate-500 mb-1">Alamat</label>
            <input v-model="form.address" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Telepon</label>
            <input v-model="form.phone" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Email</label>
            <input v-model="form.email" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <label v-if="editing" class="col-span-2 flex items-center gap-2 text-sm text-slate-600">
            <input v-model="form.active" type="checkbox" /> Aktif
          </label>
        </div>
        <p v-if="error" class="text-sm text-red-600 mt-3">{{ error }}</p>
        <button @click="save" :disabled="saving" class="w-full mt-4 py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">
          {{ saving ? 'Menyimpan…' : 'Simpan' }}
        </button>
      </div>
    </div>

    <div v-if="toast" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
