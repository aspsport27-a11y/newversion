<script setup>
import { ref, onMounted } from 'vue'
import client from '../api/client'

const areas = ref([])
const venues = ref([])
const loading = ref(false)
const toast = ref('')
const showForm = ref(false)
const editing = ref(null)
const form = ref({ code: '', name: '', is_active: true })
const busy = ref(false)

function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2500) }

async function load() {
  loading.value = true
  try {
    const [a, v] = await Promise.all([client.get('/admin/areas'), client.get('/admin/venues')])
    areas.value = a.data.areas
    venues.value = v.data.venues
  } finally { loading.value = false }
}
function openCreate() { editing.value = null; form.value = { code: '', name: '', is_active: true }; showForm.value = true }
function openEdit(a) { editing.value = a; form.value = { code: a.code, name: a.name, is_active: a.is_active }; showForm.value = true }
async function save() {
  if (!form.value.code || !form.value.name) { alert('Kode & nama wajib'); return }
  busy.value = true
  try {
    if (editing.value) await client.put(`/admin/areas/${editing.value.id}`, form.value)
    else await client.post('/admin/areas', form.value)
    showForm.value = false; await load(); flash('Area disimpan')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}
async function del(a) {
  if (!confirm(`Hapus area ${a.code} — ${a.name}?`)) return
  try { await client.delete(`/admin/areas/${a.id}`); await load(); flash('Area dihapus') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal menghapus.') }
}
async function assign(v, areaId) {
  try {
    await client.put(`/admin/venues/${v.id}`, { area_id: areaId || null })
    v.area_id = areaId || null
    await load(); flash(`${v.code} → ${areaId ? 'area diperbarui' : 'dilepas dari area'}`)
  } catch (e) { alert('Gagal mengubah area venue.') }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-800 mb-1">Area</h1>
    <p class="text-slate-500 mb-5">Kelompokkan venue ke dalam area. Dipakai untuk cakupan akses <b>Admin Unit</b> (koordinator area).</p>

    <div v-if="loading" class="text-slate-400">Memuat…</div>
    <template v-else>
      <!-- Daftar area -->
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold text-slate-700">Daftar Area</h2>
        <button @click="openCreate" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Tambah Area</button>
      </div>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden mb-8">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-2 font-medium">Kode</th>
            <th class="px-4 py-2 font-medium">Nama</th>
            <th class="px-4 py-2 font-medium text-center">Jumlah Venue</th>
            <th class="px-4 py-2 font-medium text-center">Status</th>
            <th class="px-4 py-2"></th>
          </tr></thead>
          <tbody>
            <tr v-if="!areas.length"><td colspan="5" class="px-4 py-6 text-center text-slate-400">Belum ada area.</td></tr>
            <tr v-for="a in areas" :key="a.id" class="border-t">
              <td class="px-4 py-2 font-medium text-slate-700">{{ a.code }}</td>
              <td class="px-4 py-2 text-slate-600">{{ a.name }}</td>
              <td class="px-4 py-2 text-center text-slate-600">{{ a.venue_count }}</td>
              <td class="px-4 py-2 text-center">
                <span class="text-xs px-2 py-0.5 rounded-full" :class="a.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'">{{ a.is_active ? 'Aktif' : 'Nonaktif' }}</span>
              </td>
              <td class="px-4 py-2 text-right whitespace-nowrap">
                <button @click="openEdit(a)" class="text-brand-600 hover:underline text-xs mr-3">Ubah</button>
                <button @click="del(a)" class="text-red-500 hover:text-red-700 text-xs">Hapus</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Assign venue ke area -->
      <h2 class="font-semibold text-slate-700 mb-3">Penempatan Venue ke Area</h2>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-2 font-medium">Venue</th>
            <th class="px-4 py-2 font-medium">Area</th>
          </tr></thead>
          <tbody>
            <tr v-for="v in venues" :key="v.id" class="border-t">
              <td class="px-4 py-2 text-slate-700">{{ v.code }} — {{ v.name }}</td>
              <td class="px-4 py-2">
                <select :value="v.area_id || ''" @change="assign(v, $event.target.value ? Number($event.target.value) : null)"
                  class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm outline-none focus:border-brand-500">
                  <option value="">— tanpa area —</option>
                  <option v-for="a in areas" :key="a.id" :value="a.id">{{ a.code }} — {{ a.name }}</option>
                </select>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- Form area -->
    <div v-if="showForm" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="showForm = false">
      <div class="bg-white rounded-xl shadow-lg w-full max-w-md p-5">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-slate-800">{{ editing ? 'Ubah Area' : 'Tambah Area' }}</h3>
          <button @click="showForm = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <div class="space-y-3">
          <div><label class="block text-xs text-slate-500 mb-1">Kode</label>
            <input v-model="form.code" placeholder="mis. AR1" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Nama</label>
            <input v-model="form.name" placeholder="mis. Area Jakarta" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <label class="flex items-center gap-2 text-sm text-slate-600"><input v-model="form.is_active" type="checkbox" /> Aktif</label>
        </div>
        <div class="flex gap-2 mt-5">
          <button @click="save" :disabled="busy" class="flex-1 py-2.5 rounded-lg bg-brand-600 text-white font-medium disabled:opacity-50">Simpan</button>
          <button @click="showForm = false" class="px-4 py-2.5 rounded-lg text-slate-500">Batal</button>
        </div>
      </div>
    </div>

    <div v-if="toast" class="fixed bottom-6 right-6 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
