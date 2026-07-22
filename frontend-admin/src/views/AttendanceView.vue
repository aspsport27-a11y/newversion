<script setup>
import { ref, onMounted, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isManager = computed(() => auth.user?.role === 'manager_unit')
const canDelete = computed(() => auth.hasPerm('hr.manage'))
const busy = ref(false)

const venues = ref([])
const venueId = ref('')
const rows = ref([])
const loading = ref(false)
// default rentang: 7 hari terakhir
const today = new Date().toISOString().slice(0, 10)
const weekAgo = new Date(Date.now() - 6 * 864e5).toISOString().slice(0, 10)
const from = ref(weekAgo)
const to = ref(today)

async function loadVenues() {
  const { data } = await client.get('/admin/venues')
  venues.value = data.venues
}
async function load() {
  loading.value = true
  const params = { from: from.value, to: to.value }
  if (!isManager.value && venueId.value) params.venue_id = venueId.value
  try {
    const { data } = await client.get('/admin/attendance', { params })
    rows.value = data.attendance
  } finally { loading.value = false }
}
// lihat foto absen (endpoint butuh auth → ambil blob lalu tampilkan)
const photoUrl = ref('')
const photoTitle = ref('')
async function openPhoto(row, which) {
  try {
    const { data } = await client.get(`/admin/attendance/${row.id}/photo/${which}`, { responseType: 'blob' })
    photoUrl.value = URL.createObjectURL(data)
    photoTitle.value = `${row.name} — Absen ${which === 'in' ? 'Masuk' : 'Pulang'} ${which === 'in' ? row.check_in : row.check_out}`
  } catch { alert('Foto tidak tersedia.') }
}
function closePhoto() { if (photoUrl.value) URL.revokeObjectURL(photoUrl.value); photoUrl.value = ''; }

async function deleteRow(a) {
  if (!window.confirm(`Hapus data absensi ${a.name} tanggal ${a.date}?`)) return
  busy.value = true
  try { await client.delete(`/admin/attendance/${a.id}`); await load() }
  catch (e) { alert(e?.response?.data?.message || 'Gagal menghapus.') } finally { busy.value = false }
}

// alamat lengkap dari Nominatim bisa panjang — tampilkan cuma 2 bagian
// paling spesifik (biasanya kelurahan + kecamatan), teks lengkap di title (hover)
function shortAddr(full) {
  if (!full) return ''
  return full.split(',').slice(0, 2).join(',').trim()
}

// ---- Paging ----
const page = ref(1)
const pageSize = ref(20)
const totalPages = computed(() => Math.max(1, Math.ceil(rows.value.length / pageSize.value)))
const paged = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return rows.value.slice(start, start + pageSize.value)
})
function applyFilter() { page.value = 1; load() }

onMounted(async () => { await loadVenues(); await load() })
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-800 mb-1">Absensi</h1>
    <p class="text-slate-500 mb-5">Rekap kehadiran staff — dari absen PIN di terminal POS (waktu WITA).</p>

    <div class="bg-white rounded-xl shadow-sm border p-4 mb-5 flex flex-wrap items-end gap-3">
      <div><label class="block text-xs text-slate-500 mb-1">Dari</label>
        <input v-model="from" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <div><label class="block text-xs text-slate-500 mb-1">Sampai</label>
        <input v-model="to" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <div v-if="!isManager"><label class="block text-xs text-slate-500 mb-1">Venue</label>
        <select v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua venue (cakupan saya)</option>
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select></div>
      <button @click="applyFilter" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-5 py-2 font-medium">Terapkan</button>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-2 font-medium">Tanggal</th>
            <th class="px-4 py-2 font-medium">Nama</th>
            <th class="px-4 py-2 font-medium">Venue</th>
            <th class="px-4 py-2 font-medium text-center">Masuk</th>
            <th class="px-4 py-2 font-medium text-center">Pulang</th>
            <th class="px-4 py-2 font-medium">Lokasi</th>
            <th class="px-4 py-2 font-medium text-right">Jam Kerja</th>
            <th v-if="canDelete" class="px-4 py-2"></th>
          </tr></thead>
          <tbody>
            <tr v-if="loading"><td :colspan="canDelete ? 8 : 7" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!rows.length"><td :colspan="canDelete ? 8 : 7" class="px-4 py-8 text-center text-slate-400">Belum ada data absen pada rentang ini.</td></tr>
            <tr v-for="a in paged" :key="a.id" class="border-t">
              <td class="px-4 py-2 text-slate-500">{{ a.date }}</td>
              <td class="px-4 py-2 text-slate-700 font-medium">{{ a.name }}</td>
              <td class="px-4 py-2 text-slate-500">{{ a.venue_code || '—' }}</td>
              <td class="px-4 py-2 text-center whitespace-nowrap">
                <span :class="a.check_in ? 'text-emerald-700' : 'text-slate-300'">{{ a.check_in || '—' }}</span>
                <button v-if="a.has_in_photo" @click="openPhoto(a, 'in')" title="Lihat foto" class="ml-1">📷</button>
              </td>
              <td class="px-4 py-2 text-center whitespace-nowrap">
                <span :class="a.check_out ? 'text-slate-700' : 'text-amber-500'">{{ a.check_out || 'belum' }}</span>
                <button v-if="a.has_out_photo" @click="openPhoto(a, 'out')" title="Lihat foto" class="ml-1">📷</button>
              </td>
              <td class="px-4 py-2 text-xs max-w-[220px]">
                <a v-if="a.check_in_location" :href="`https://www.google.com/maps?q=${a.check_in_location}`" target="_blank" rel="noopener"
                  :title="a.check_in_address || ''" class="block text-brand-600 hover:underline truncate">
                  📍 {{ shortAddr(a.check_in_address) || 'Masuk' }}
                </a>
                <a v-if="a.check_out_location" :href="`https://www.google.com/maps?q=${a.check_out_location}`" target="_blank" rel="noopener"
                  :title="a.check_out_address || ''" class="block text-brand-600 hover:underline truncate">
                  📍 {{ shortAddr(a.check_out_address) || 'Pulang' }}
                </a>
                <span v-if="!a.check_in_location && !a.check_out_location" class="text-slate-300">—</span>
              </td>
              <td class="px-4 py-2 text-right text-slate-600">{{ a.work_hours != null ? a.work_hours + ' jam' : '—' }}</td>
              <td v-if="canDelete" class="px-4 py-2 text-right">
                <button @click="deleteRow(a)" :disabled="busy" class="text-red-500 hover:underline text-xs disabled:opacity-50">Hapus</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="rows.length" class="flex items-center justify-between gap-3 px-4 py-3 border-t flex-wrap">
        <p class="text-xs text-slate-500">
          Menampilkan {{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, rows.length) }} dari {{ rows.length }} data
        </p>
        <div class="flex items-center gap-2">
          <select v-model.number="pageSize" @change="page = 1" class="rounded-lg border border-slate-300 px-2 py-1.5 text-xs outline-none focus:border-brand-500">
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

    <!-- Foto absen -->
    <div v-if="photoUrl" class="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" @click.self="closePhoto">
      <div class="bg-white rounded-2xl p-4 max-w-sm w-full">
        <div class="flex justify-between items-center mb-2">
          <p class="text-sm font-medium text-slate-700">{{ photoTitle }}</p>
          <button @click="closePhoto" class="text-slate-400 text-xl">✕</button>
        </div>
        <img :src="photoUrl" alt="Foto absen" class="w-full rounded-lg" />
      </div>
    </div>
  </div>
</template>
