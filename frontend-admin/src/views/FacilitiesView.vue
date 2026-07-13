<script setup>
import { ref, onMounted, watch } from 'vue'
import client from '../api/client'

const venues = ref([])
const venueId = ref(null)
const facilities = ref([])
const loading = ref(false)
const showForm = ref(false)
const editing = ref(null)
const form = ref({})
const error = ref('')
const saving = ref(false)

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }

async function loadVenues() {
  const { data } = await client.get('/admin/venues')
  venues.value = data.venues
  if (venues.value.length && !venueId.value) venueId.value = venues.value[0].id
}
async function loadFacilities() {
  if (!venueId.value) return
  loading.value = true
  try {
    const { data } = await client.get('/admin/facilities', { params: { venue_id: venueId.value } })
    facilities.value = data.facilities
  } finally { loading.value = false }
}
onMounted(async () => { await loadVenues(); await loadFacilities() })
watch(venueId, loadFacilities)

function openCreate() {
  editing.value = null
  form.value = { name: '', type: '', hourly_rate: 0, open_time: '08:00', close_time: '23:00', is_active: true }
  error.value = ''; showForm.value = true
}
function openEdit(f) {
  editing.value = f
  form.value = { name: f.name, type: f.type, hourly_rate: f.hourly_rate, open_time: f.open_time, close_time: f.close_time, is_active: f.is_active }
  error.value = ''; showForm.value = true
}
async function save() {
  saving.value = true; error.value = ''
  try {
    if (editing.value) await client.put(`/admin/facilities/${editing.value.id}`, form.value)
    else await client.post('/admin/facilities', { ...form.value, venue_id: venueId.value })
    showForm.value = false
    await loadFacilities()
  } catch (e) {
    error.value = e?.response?.data?.message || 'Gagal menyimpan.'
  } finally { saving.value = false }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-6">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">Lapangan</h1>
        <p class="text-slate-500 mt-1">Kelola lapangan yang bisa dibooking per venue.</p>
      </div>
      <div class="flex gap-2">
        <select v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select>
        <button @click="openCreate" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Lapangan</button>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th class="px-4 py-3 font-medium">Nama</th>
              <th class="px-4 py-3 font-medium">Tipe</th>
              <th class="px-4 py-3 font-medium text-right">Tarif/jam</th>
              <th class="px-4 py-3 font-medium">Jam Operasi</th>
              <th class="px-4 py-3 font-medium text-center">Status</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!facilities.length"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Belum ada lapangan.</td></tr>
            <tr v-for="f in facilities" :key="f.id" class="border-t hover:bg-slate-50">
              <td class="px-4 py-3 font-medium text-slate-700">{{ f.name }}</td>
              <td class="px-4 py-3 text-slate-500">{{ f.type || '—' }}</td>
              <td class="px-4 py-3 text-right">{{ rupiah(f.hourly_rate) }}</td>
              <td class="px-4 py-3 text-slate-600">{{ f.open_time }}–{{ f.close_time }}</td>
              <td class="px-4 py-3 text-center">
                <span :class="f.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="text-xs rounded-full px-2 py-0.5">
                  {{ f.is_active ? 'Aktif' : 'Nonaktif' }}
                </span>
              </td>
              <td class="px-4 py-3 text-right">
                <button @click="openEdit(f)" class="text-brand-600 text-sm hover:underline">Edit</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="showForm" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-md rounded-2xl p-5">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-slate-800">{{ editing ? 'Edit Lapangan' : 'Lapangan Baru' }}</h3>
          <button @click="showForm = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <div class="space-y-3">
          <input v-model="form.name" placeholder="Nama (mis. Lapangan A)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <input v-model="form.type" placeholder="Tipe (mis. futsal, padel)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <input v-model.number="form.hourly_rate" type="number" placeholder="Tarif per jam" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <div class="grid grid-cols-2 gap-2">
            <div><label class="text-xs text-slate-500">Buka</label><input v-model="form.open_time" type="time" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
            <div><label class="text-xs text-slate-500">Tutup</label><input v-model="form.close_time" type="time" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          </div>
          <label class="flex items-center gap-2 text-sm text-slate-600">
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
