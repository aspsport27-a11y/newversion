<script setup>
import { ref, onMounted } from 'vue'
import client from '../api/client'

const venues = ref([])
const venueId = ref('')
const today = new Date().toISOString().slice(0, 10)
const in30 = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10)
const from = ref(today)
const to = ref(in30)
const bookings = ref([])
const loading = ref(false)

function venueCode(id) { const v = venues.value.find((x) => x.id === id); return v ? v.code : '—' }
function fmtDate(d) {
  return new Date(d + 'T00:00:00').toLocaleDateString('id-ID', { weekday: 'short', day: '2-digit', month: 'short' })
}

async function loadVenues() {
  const { data } = await client.get('/admin/venues')
  venues.value = data.venues
}
async function run() {
  loading.value = true
  const params = { from: from.value, to: to.value }
  if (venueId.value) params.venue_id = venueId.value
  try {
    const { data } = await client.get('/admin/bookings', { params })
    bookings.value = data.bookings
  } finally { loading.value = false }
}
onMounted(async () => { await loadVenues(); await run() })
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-800 mb-1">Booking Lapangan</h1>
    <p class="text-slate-500 mb-5">Jadwal booking lapangan dari semua transaksi.</p>

    <div class="bg-white rounded-xl shadow-sm border p-4 mb-5 flex flex-wrap items-end gap-3">
      <div><label class="block text-xs text-slate-500 mb-1">Dari</label>
        <input v-model="from" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <div><label class="block text-xs text-slate-500 mb-1">Sampai</label>
        <input v-model="to" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <div><label class="block text-xs text-slate-500 mb-1">Venue</label>
        <select v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua venue</option>
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select></div>
      <button @click="run" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-5 py-2 font-medium">Terapkan</button>
      <span class="text-sm text-slate-400 ml-auto">{{ bookings.length }} booking</span>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th class="px-4 py-3 font-medium">Tanggal</th>
              <th class="px-4 py-3 font-medium">Jam</th>
              <th class="px-4 py-3 font-medium">Lapangan</th>
              <th class="px-4 py-3 font-medium">Venue</th>
              <th class="px-4 py-3 font-medium">Customer</th>
              <th class="px-4 py-3 font-medium">No. Order</th>
              <th class="px-4 py-3 font-medium text-center">Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading"><td colspan="7" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!bookings.length"><td colspan="7" class="px-4 py-8 text-center text-slate-400">Belum ada booking pada rentang ini.</td></tr>
            <tr v-for="b in bookings" :key="b.id" class="border-t hover:bg-slate-50">
              <td class="px-4 py-3 text-slate-700">{{ fmtDate(b.booking_date) }}</td>
              <td class="px-4 py-3 font-medium text-slate-700">{{ b.start_time }}–{{ b.end_time }}</td>
              <td class="px-4 py-3 text-slate-700">{{ b.facility_name }}</td>
              <td class="px-4 py-3 text-slate-500">{{ venueCode(b.venue_id) }}</td>
              <td class="px-4 py-3 text-slate-600">{{ b.customer_name || '—' }}</td>
              <td class="px-4 py-3 font-mono text-xs text-slate-500">{{ b.order_number || '—' }}</td>
              <td class="px-4 py-3 text-center">
                <span :class="b.status === 'booked' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="text-xs rounded-full px-2 py-0.5">
                  {{ b.status === 'booked' ? 'Terpakai' : b.status }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
