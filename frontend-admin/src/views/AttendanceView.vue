<script setup>
import { ref, onMounted, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isManager = computed(() => auth.user?.role === 'manager_unit')

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
      <button @click="load" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-5 py-2 font-medium">Terapkan</button>
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
            <th class="px-4 py-2 font-medium text-right">Jam Kerja</th>
          </tr></thead>
          <tbody>
            <tr v-if="loading"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!rows.length"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Belum ada data absen pada rentang ini.</td></tr>
            <tr v-for="a in rows" :key="a.id" class="border-t">
              <td class="px-4 py-2 text-slate-500">{{ a.date }}</td>
              <td class="px-4 py-2 text-slate-700 font-medium">{{ a.name }}</td>
              <td class="px-4 py-2 text-slate-500">{{ a.venue_code || '—' }}</td>
              <td class="px-4 py-2 text-center">
                <span :class="a.check_in ? 'text-emerald-700' : 'text-slate-300'">{{ a.check_in || '—' }}</span>
              </td>
              <td class="px-4 py-2 text-center">
                <span :class="a.check_out ? 'text-slate-700' : 'text-amber-500'">{{ a.check_out || 'belum' }}</span>
              </td>
              <td class="px-4 py-2 text-right text-slate-600">{{ a.work_hours != null ? a.work_hours + ' jam' : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
