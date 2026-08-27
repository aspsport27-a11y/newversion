<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'
import { parseUTC } from '../utils/datetime'

const auth = useAuthStore()
const toast = useToastStore()
function flash(m) { toast.show(m) }
const isManager = computed(() => auth.user?.role === 'manager_unit')

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
const today = new Date().toISOString().slice(0, 10)

const venues = ref([])
const venueId = ref('')
const scope = ref('upcoming')
const events = ref([])
const loading = ref(false)

async function loadVenues() {
  const { data } = await client.get('/venues')
  venues.value = data.venues
  if (isManager.value) { venues.value = venues.value.filter((v) => v.id === auth.user?.venue_id); venueId.value = auth.user?.venue_id || '' }
}
async function load() {
  loading.value = true
  try {
    const params = { scope: scope.value }
    if (!isManager.value && venueId.value) params.venue_id = venueId.value
    const { data } = await client.get('/admin/events', { params })
    events.value = data.events
  } finally { loading.value = false }
}
onMounted(async () => { await loadVenues(); await load() })
watch([venueId, scope], load)

function venueName(id) { const v = venues.value.find((x) => x.id === id); return v ? v.code : '—' }
function fmtRange(e) {
  const d = e.date_from === e.date_to ? e.date_from : `${e.date_from} → ${e.date_to}`
  return `${d} · ${e.start_time}–${e.end_time}`
}
const payLabel = { paid: 'Lunas', partial: 'DP', open: 'Belum bayar' }

// ---- Create ----
const showCreate = ref(false)
const cForm = ref({})
const cQuote = ref({ suggested_price: 0, facility_count: 0, conflict_count: 0 })
const cSaving = ref(false)
const cErr = ref('')
let quoteTimer = null
function openCreate() {
  cForm.value = {
    venue_id: isManager.value ? auth.user?.venue_id : (venueId.value || venues.value[0]?.id),
    name: '', renter: '', phone: '',
    date_from: today, date_to: today, start_time: '08:00', end_time: '17:00', price: null,
  }
  cQuote.value = { suggested_price: 0, facility_count: 0, conflict_count: 0 }
  cErr.value = ''; showCreate.value = true
}
function cValid() {
  const f = cForm.value
  return f.venue_id && f.name?.trim() && f.date_to >= f.date_from && f.end_time > f.start_time
}
async function refreshQuote() {
  if (!cValid()) return
  try {
    const { data } = await client.get('/admin/events/quote', { params: {
      venue_id: cForm.value.venue_id, date_from: cForm.value.date_from, date_to: cForm.value.date_to,
      start_time: cForm.value.start_time, end_time: cForm.value.end_time,
    } })
    cQuote.value = data
    if (cForm.value.price === null || cForm.value.price === '') cForm.value.price = data.suggested_price
  } catch { /* */ }
}
watch(() => [cForm.value.venue_id, cForm.value.date_from, cForm.value.date_to, cForm.value.start_time, cForm.value.end_time], () => {
  if (!showCreate.value) return
  clearTimeout(quoteTimer); quoteTimer = setTimeout(refreshQuote, 400)
})
async function submitCreate() {
  if (!cValid()) { cErr.value = 'Lengkapi nama, tanggal, dan jam (selesai > mulai).'; return }
  cSaving.value = true; cErr.value = ''
  try {
    const { data } = await client.post('/admin/events', { ...cForm.value, price: Number(cForm.value.price) || 0 })
    showCreate.value = false
    await load()
    flash(`Event dibuat. ${data.conflicts.length} booking bentrok.`)
    openDetail({ id: data.event.id })
  } catch (e) { cErr.value = e?.response?.data?.message || 'Gagal.' } finally { cSaving.value = false }
}

// ---- Detail ----
const detail = ref(null)          // { event, conflicts }
async function openDetail(e) {
  const { data } = await client.get(`/admin/events/${e.id}`)
  detail.value = data
}
async function toggleContacted(c) {
  try {
    const { data } = await client.post(`/admin/events/${detail.value.event.id}/contacted`, { order_id: c.order_id })
    c.contacted = data.contacted
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') }
}
async function cancelEvent(e) {
  if (!window.confirm(`Batalkan event "${e.name}"? Jadwal jam ini akan terbuka kembali untuk booking.`)) return
  try {
    await client.post(`/admin/events/${e.id}/cancel`)
    detail.value = null
    await load()
    flash('Event dibatalkan.')
  } catch (err) { alert(err?.response?.data?.message || 'Gagal.') }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-5">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">🏆 Event</h1>
        <p class="text-slate-500 mt-1">Sewa borongan / turnamen — mengunci semua lapangan; booking bentrok dipindah jadwal.</p>
      </div>
      <button @click="openCreate" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Buat Event</button>
    </div>

    <div class="bg-white rounded-xl shadow-sm border p-4 mb-5 flex flex-wrap items-end gap-3">
      <div v-if="!isManager"><label class="block text-xs text-slate-500 mb-1">Venue</label>
        <select v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua venue</option>
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select></div>
      <div><label class="block text-xs text-slate-500 mb-1">Tampilkan</label>
        <select v-model="scope" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="upcoming">Mendatang & aktif</option>
          <option value="all">Semua (termasuk lampau/batal)</option>
        </select></div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-3 font-medium">Event</th>
            <th v-if="!isManager" class="px-4 py-3 font-medium">Venue</th>
            <th class="px-4 py-3 font-medium">Jadwal</th>
            <th class="px-4 py-3 font-medium text-right">Harga</th>
            <th class="px-4 py-3 font-medium text-center">Bayar</th>
            <th class="px-4 py-3 font-medium text-center">Bentrok</th>
            <th class="px-4 py-3"></th>
          </tr></thead>
          <tbody>
            <tr v-if="loading"><td colspan="7" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!events.length"><td colspan="7" class="px-4 py-8 text-center text-slate-400">Belum ada event.</td></tr>
            <tr v-for="e in events" :key="e.id" @click="openDetail(e)" class="border-t hover:bg-slate-50 cursor-pointer" :class="e.status === 'cancelled' ? 'opacity-50' : ''">
              <td class="px-4 py-3">
                <div class="font-medium text-slate-800">{{ e.name }} <span v-if="e.status === 'cancelled'" class="text-xs text-red-500">(dibatalkan)</span></div>
                <div class="text-xs text-slate-400">{{ e.renter || '—' }}{{ e.phone ? ' · ' + e.phone : '' }}</div>
              </td>
              <td v-if="!isManager" class="px-4 py-3 text-slate-600">{{ venueName(e.venue_id) }}</td>
              <td class="px-4 py-3 text-slate-600 whitespace-nowrap">{{ fmtRange(e) }}</td>
              <td class="px-4 py-3 text-right font-medium">{{ rupiah(e.price) }}</td>
              <td class="px-4 py-3 text-center">
                <span class="text-xs rounded-full px-2 py-0.5" :class="e.order_status === 'paid' ? 'bg-emerald-100 text-emerald-700' : (e.order_status === 'partial' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500')">{{ payLabel[e.order_status] || '—' }}</span>
              </td>
              <td class="px-4 py-3 text-center">
                <span v-if="e.conflict_count" class="text-xs rounded-full px-2 py-0.5 bg-red-100 text-red-700 font-medium">⚠️ {{ e.conflict_count }}</span>
                <span v-else class="text-slate-300 text-xs">—</span>
              </td>
              <td class="px-4 py-3 text-right text-brand-600 text-sm">Detail</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Create modal -->
    <div v-if="showCreate" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="showCreate = false">
      <div class="bg-white w-full max-w-md rounded-2xl p-5 max-h-[92vh] overflow-auto">
        <div class="flex justify-between items-center mb-3"><h3 class="text-lg font-bold text-slate-800">🏆 Buat Event</h3><button @click="showCreate = false" class="text-slate-400 text-xl">✕</button></div>
        <div class="space-y-3">
          <div v-if="!isManager"><label class="text-xs text-slate-500">Venue</label>
            <select v-model="cForm.venue_id" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none">
              <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
            </select></div>
          <div><label class="text-xs text-slate-500">Nama event</label>
            <input v-model="cForm.name" placeholder="mis. Turnamen Futsal RT 05" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none" /></div>
          <div class="grid grid-cols-2 gap-2">
            <div><label class="text-xs text-slate-500">Penyewa</label><input v-model="cForm.renter" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none" /></div>
            <div><label class="text-xs text-slate-500">No. HP</label><input v-model="cForm.phone" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none" /></div>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div><label class="text-xs text-slate-500">Tanggal mulai</label><input v-model="cForm.date_from" type="date" class="w-full rounded-lg border border-slate-300 px-2 py-2 text-sm outline-none" /></div>
            <div><label class="text-xs text-slate-500">Tanggal selesai</label><input v-model="cForm.date_to" type="date" :min="cForm.date_from" class="w-full rounded-lg border border-slate-300 px-2 py-2 text-sm outline-none" /></div>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div><label class="text-xs text-slate-500">Jam mulai</label><input v-model="cForm.start_time" type="time" class="w-full rounded-lg border border-slate-300 px-2 py-2 text-sm outline-none" /></div>
            <div><label class="text-xs text-slate-500">Jam selesai</label><input v-model="cForm.end_time" type="time" class="w-full rounded-lg border border-slate-300 px-2 py-2 text-sm outline-none" /></div>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-lg p-3">
            <div class="flex justify-between text-xs text-slate-500 mb-1">
              <span>{{ cQuote.facility_count }} lapangan • harga normal</span>
              <span v-if="cQuote.conflict_count" class="text-amber-600 font-medium">⚠️ {{ cQuote.conflict_count }} bentrok</span>
            </div>
            <label class="text-xs text-slate-500">Harga sewa (bisa nego)</label>
            <div class="flex gap-2 items-center">
              <input v-model.number="cForm.price" type="number" class="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-lg text-right outline-none" />
              <button @click="cForm.price = cQuote.suggested_price" type="button" class="text-xs text-brand-600 whitespace-nowrap">usulan<br />{{ rupiah(cQuote.suggested_price) }}</button>
            </div>
            <p class="text-[11px] text-slate-400 mt-1">Order dibuat belum lunas → tagih di POS (menu Pelunasan).</p>
          </div>
          <p v-if="cErr" class="text-sm text-red-600">{{ cErr }}</p>
          <button @click="submitCreate" :disabled="cSaving" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">{{ cSaving ? 'Menyimpan…' : 'Buat Event' }}</button>
        </div>
      </div>
    </div>

    <!-- Detail modal -->
    <div v-if="detail" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="detail = null">
      <div class="bg-white w-full max-w-lg rounded-2xl p-5 max-h-[92vh] overflow-auto">
        <div class="flex justify-between items-start mb-2">
          <div>
            <h3 class="text-lg font-bold text-slate-800">{{ detail.event.name }}</h3>
            <p class="text-sm text-slate-500">{{ fmtRange(detail.event) }}</p>
            <p class="text-xs text-slate-400">{{ detail.event.renter || '—' }}{{ detail.event.phone ? ' · ' + detail.event.phone : '' }}</p>
          </div>
          <button @click="detail = null" class="text-slate-400 hover:text-slate-600 text-xl">✕</button>
        </div>
        <div class="flex flex-wrap gap-3 text-sm bg-slate-50 rounded-lg px-3 py-2 mb-3">
          <span>Harga: <b>{{ rupiah(detail.event.price) }}</b></span>
          <span>Bayar: <b>{{ payLabel[detail.event.order_status] || '—' }}</b></span>
          <span v-if="detail.event.amount_due > 0" class="text-amber-600">Sisa: {{ rupiah(detail.event.amount_due) }}</span>
        </div>

        <p class="text-sm font-medium text-slate-700 mb-1">Booking terdampak (perlu dipindah)</p>
        <p v-if="!detail.conflicts.length" class="text-sm text-slate-400 mb-3">Tidak ada yang bentrok 🎉</p>
        <div v-else class="space-y-2 mb-3">
          <div v-for="c in detail.conflicts" :key="c.booking_id" class="border rounded-lg p-2 flex justify-between items-center gap-2">
            <div class="text-sm min-w-0">
              <p class="font-medium text-slate-800 truncate">{{ c.customer_name || 'Tanpa nama' }}
                <span v-if="c.is_member" class="text-[10px] bg-purple-100 text-purple-700 rounded px-1">member</span>
                <span v-if="c.customer_phone" class="text-xs text-slate-400"> · {{ c.customer_phone }}</span>
              </p>
              <p class="text-xs text-slate-500">{{ c.facility_name }} · {{ c.booking_date }} {{ c.start_time }}-{{ c.end_time }}</p>
            </div>
            <button @click="toggleContacted(c)" class="text-xs rounded-lg px-2.5 py-1.5 font-medium whitespace-nowrap"
              :class="c.contacted ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'">
              {{ c.contacted ? '✅ Dihubungi' : 'Tandai dihubungi' }}
            </button>
          </div>
          <p class="text-[11px] text-slate-400">Pemindahan jadwal (reschedule) dilakukan di POS (menu Pelunasan → Reschedule) atau menu Booking.</p>
        </div>

        <div v-if="detail.event.status === 'active'" class="flex gap-2 pt-2 border-t">
          <button @click="cancelEvent(detail.event)" class="flex-1 py-2 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 font-medium">Batalkan Event</button>
        </div>
        <p v-else class="text-sm text-red-500 text-center pt-2 border-t">Event dibatalkan.</p>
      </div>
    </div>
  </div>
</template>
