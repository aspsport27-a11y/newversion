<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isAdminUnit = computed(() => auth.user?.role === 'admin_unit')
const isManager = computed(() => auth.user?.role === 'manager_unit')

const venues = ref([])
const venueId = ref(null)
const loading = ref(false)
const toast = ref('')
function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2500) }
function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }

const currentVenue = computed(() => venues.value.find((v) => v.id === venueId.value))
// tipe venue tiket = waterpark; lainnya = venue lapangan (booking)
const isTicketVenue = computed(() => /water/i.test(currentVenue.value?.type || ''))
const tab = ref('lapangan')

async function loadVenues() {
  const { data } = await client.get('/venues')
  venues.value = data.venues
  // manager_unit dibatasi ke venue-nya sendiri; admin_unit hanya venue di areanya
  if (isManager.value) venues.value = venues.value.filter((x) => x.id === auth.user?.venue_id)
  else if (isAdminUnit.value) venues.value = venues.value.filter((x) => x.area_id === auth.user?.area_id)
  if (venues.value.length && !venueId.value) venueId.value = venues.value[0].id
}

// ---------------- LAPANGAN ----------------
const facilities = ref([])
const showFac = ref(false)
const editingFac = ref(null)
const facForm = ref({})
const facErr = ref('')
const savingFac = ref(false)
async function loadFacilities() {
  if (!venueId.value) return
  const { data } = await client.get('/admin/facilities', { params: { venue_id: venueId.value } })
  facilities.value = data.facilities
}
function openFac(f = null) {
  editingFac.value = f
  facForm.value = f
    ? { name: f.name, type: f.type, hourly_rate: f.hourly_rate, open_time: f.open_time, close_time: f.close_time, is_active: f.is_active }
    : { name: '', type: '', hourly_rate: 0, open_time: '08:00', close_time: '23:00', is_active: true }
  facErr.value = ''; showFac.value = true
}
async function saveFac() {
  savingFac.value = true; facErr.value = ''
  try {
    if (editingFac.value) await client.put(`/admin/facilities/${editingFac.value.id}`, facForm.value)
    else await client.post('/admin/facilities', { ...facForm.value, venue_id: venueId.value })
    showFac.value = false; await loadFacilities(); flash('Lapangan disimpan')
  } catch (e) { facErr.value = e?.response?.data?.message || 'Gagal.' } finally { savingFac.value = false }
}

// ---------------- TARIF PER JAM (facility_rate_rules) ----------------
const showRates = ref(false)
const rateFac = ref(null)
const rateRules = ref([])
const rateForm = ref({ label: '', day_type: 'weekday', start_time: '', end_time: '', hourly_rate: 0 })
const DAY_LABELS = { weekday: 'Weekday', thursday: 'Kamis', saturday: 'Sabtu', sunday: 'Minggu', holiday: 'Libur' }
const rateErr = ref('')
const savingRate = ref(false)
async function openRates(f) {
  rateFac.value = f
  rateForm.value = { label: '', day_type: 'weekday', start_time: '', end_time: '', hourly_rate: f.hourly_rate }
  rateErr.value = ''
  showRates.value = true
  await loadRateRules()
}
async function loadRateRules() {
  if (!rateFac.value) return
  const { data } = await client.get(`/admin/facilities/${rateFac.value.id}/rate-rules`)
  rateRules.value = data.rate_rules
}
async function addRateRule() {
  rateErr.value = ''
  if (!rateForm.value.start_time || !rateForm.value.end_time) { rateErr.value = 'Jam mulai & selesai wajib diisi.'; return }
  savingRate.value = true
  try {
    await client.post(`/admin/facilities/${rateFac.value.id}/rate-rules`, rateForm.value)
    rateForm.value = { label: '', start_time: '', end_time: '', hourly_rate: rateFac.value.hourly_rate }
    await loadRateRules()
    await loadFacilities()
    flash('Aturan tarif ditambah')
  } catch (e) { rateErr.value = e?.response?.data?.message || 'Gagal.' } finally { savingRate.value = false }
}
async function delRateRule(r) {
  if (!confirm(`Hapus tarif "${r.label || r.start_time + '-' + r.end_time}"?`)) return
  try {
    await client.delete(`/admin/rate-rules/${r.id}`)
    await loadRateRules()
    await loadFacilities()
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') }
}

// ---------------- TIKET (produk is_ticket) ----------------
const tickets = ref([])
const showTk = ref(false)
const editingTk = ref(null)
const tkForm = ref({})
const tkErr = ref('')
const savingTk = ref(false)
async function loadTickets() {
  if (!venueId.value) return
  const { data } = await client.get('/admin/products', { params: { venue_id: venueId.value, ticket: 1 } })
  tickets.value = data.products
}
function openTk(t = null) {
  editingTk.value = t
  tkForm.value = t
    ? { name: t.name, price: t.price, weekend_price: t.weekend_price, is_active: t.is_active }
    : { name: '', price: 0, weekend_price: null, is_active: true }
  tkErr.value = ''; showTk.value = true
}
async function saveTk() {
  if (!tkForm.value.name) { tkErr.value = 'Nama tiket wajib'; return }
  savingTk.value = true; tkErr.value = ''
  try {
    if (editingTk.value) {
      await client.put(`/admin/products/${editingTk.value.id}`, tkForm.value)
    } else {
      await client.post('/admin/products', { ...tkForm.value, venue_id: venueId.value, is_ticket: true, track_stock: false, category: 'Tiket' })
    }
    showTk.value = false; await loadTickets(); flash('Tiket disimpan')
  } catch (e) { tkErr.value = e?.response?.data?.message || 'Gagal.' } finally { savingTk.value = false }
}

// ---------------- HARI LIBUR (global) ----------------
const holidays = ref([])
const holForm = ref({ date: '', name: '' })
const savingHol = ref(false)
async function loadHolidays() {
  const { data } = await client.get('/admin/holidays')
  holidays.value = data.holidays
}
async function addHoliday() {
  if (!holForm.value.date) return
  savingHol.value = true
  try {
    await client.post('/admin/holidays', holForm.value)
    holForm.value = { date: '', name: '' }
    await loadHolidays(); flash('Hari libur ditambah')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { savingHol.value = false }
}
async function delHoliday(h) {
  if (!confirm(`Hapus ${h.date}${h.name ? ' — ' + h.name : ''}?`)) return
  try { await client.delete(`/admin/holidays/${h.id}`); await loadHolidays() } catch { alert('Gagal.') }
}

// ---------------- COACHING (padel) ----------------
const coaches = ref([])
const coachRate = ref(null)
const rateFormC = ref({ base_price: 0, extra_person_price: 0, max_persons: 4 })
const savingRateC = ref(false)
const coachForm = ref({ name: '', phone: '', is_active: true })
const editingCoach = ref(null)
const showCoach = ref(false)
const coachErr = ref('')
const savingCoach = ref(false)

async function loadCoaching() {
  if (!venueId.value) return
  try {
    const [c, r] = await Promise.all([
      client.get('/admin/coaches', { params: { venue_id: venueId.value } }),
      client.get('/admin/coaching-rate', { params: { venue_id: venueId.value } }),
    ])
    coaches.value = c.data.coaches
    coachRate.value = r.data.rate
    rateFormC.value = r.data.rate
      ? { base_price: r.data.rate.base_price, extra_person_price: r.data.rate.extra_person_price, max_persons: r.data.rate.max_persons }
      : { base_price: 0, extra_person_price: 0, max_persons: 4 }
  } catch (_) {
    coaches.value = []; coachRate.value = null
  }
}
async function saveCoachRate() {
  savingRateC.value = true
  try {
    await client.put('/admin/coaching-rate', { ...rateFormC.value, venue_id: venueId.value })
    await loadCoaching(); flash('Tarif coaching disimpan')
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { savingRateC.value = false }
}
// contoh harga per jumlah peserta — biar manajer lihat efek tarif sebelum simpan
const coachPricePreview = computed(() => {
  const b = Number(rateFormC.value.base_price) || 0
  const e = Number(rateFormC.value.extra_person_price) || 0
  const max = Math.min(Number(rateFormC.value.max_persons) || 4, 10)
  return Array.from({ length: max }, (_, i) => ({ n: i + 1, price: b + i * e }))
})
function openCoach(c = null) {
  editingCoach.value = c
  coachForm.value = c ? { name: c.name, phone: c.phone || '', is_active: c.is_active } : { name: '', phone: '', is_active: true }
  coachErr.value = ''; showCoach.value = true
}
async function saveCoach() {
  savingCoach.value = true; coachErr.value = ''
  try {
    if (editingCoach.value) await client.put(`/admin/coaches/${editingCoach.value.id}`, coachForm.value)
    else await client.post('/admin/coaches', { ...coachForm.value, venue_id: venueId.value })
    showCoach.value = false; await loadCoaching(); flash('Coach disimpan')
  } catch (e) { coachErr.value = e?.response?.data?.message || 'Gagal.' } finally { savingCoach.value = false }
}
async function delCoach(c) {
  if (!confirm(`Hapus coach ${c.name}?`)) return
  try { await client.delete(`/admin/coaches/${c.id}`); await loadCoaching() }
  catch (e) { alert(e?.response?.data?.message || 'Gagal.') }
}

function reload() {
  // set tab default sesuai tipe venue
  tab.value = isTicketVenue.value ? 'tiket' : 'lapangan'
  if (isTicketVenue.value) { loadTickets(); loadHolidays() } else { loadFacilities(); loadCoaching() }
}
onMounted(async () => { loading.value = true; await loadVenues(); reload(); loading.value = false })
watch(venueId, reload)
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-5">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">Lapangan &amp; Tiket</h1>
        <p class="text-slate-500 mt-1">Kelola lapangan (booking) atau tiket (waterpark) per venue.</p>
      </div>
      <select v-if="!isManager" v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
        <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
      </select>
    </div>

    <!-- Tabs (otomatis sesuai tipe venue) -->
    <div class="flex gap-1 mb-4 border-b">
      <template v-if="isTicketVenue">
        <button @click="tab = 'tiket'" :class="tab === 'tiket' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Tiket</button>
        <button @click="tab = 'libur'" :class="tab === 'libur' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Hari Libur</button>
      </template>
      <template v-else>
        <button @click="tab = 'lapangan'" :class="tab === 'lapangan' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Lapangan</button>
        <button @click="tab = 'coaching'" :class="tab === 'coaching' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Coaching</button>
      </template>
    </div>

    <div v-if="loading" class="text-slate-400">Memuat…</div>

    <!-- ===== LAPANGAN ===== -->
    <div v-else-if="tab === 'lapangan'">
      <div class="flex justify-end mb-3"><button @click="openFac()" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Lapangan</button></div>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-3 font-medium">Nama</th><th class="px-4 py-3 font-medium">Tipe</th>
            <th class="px-4 py-3 font-medium text-right">Tarif/jam</th><th class="px-4 py-3 font-medium">Jam</th>
            <th class="px-4 py-3 font-medium text-center">Status</th><th class="px-4 py-3"></th>
          </tr></thead>
          <tbody>
            <tr v-if="!facilities.length"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Belum ada lapangan.</td></tr>
            <tr v-for="f in facilities" :key="f.id" class="border-t hover:bg-slate-50">
              <td class="px-4 py-3 font-medium text-slate-700">{{ f.name }}</td>
              <td class="px-4 py-3 text-slate-500">{{ f.type || '—' }}</td>
              <td class="px-4 py-3 text-right">
                <template v-if="f.rate_rules?.length">
                  <div v-for="r in f.rate_rules" :key="r.id" class="text-xs text-slate-600 whitespace-nowrap">
                    <span class="text-[10px] text-brand-600">[{{ DAY_LABELS[r.day_type] || r.day_type }}]</span>
                    {{ r.start_time }}–{{ r.end_time }}<span v-if="r.label"> ({{ r.label }})</span>: {{ rupiah(r.hourly_rate) }}
                  </div>
                  <div v-if="f.hourly_rate" class="text-xs text-slate-400">jam lain: {{ rupiah(f.hourly_rate) }}</div>
                </template>
                <template v-else>{{ rupiah(f.hourly_rate) }}</template>
              </td>
              <td class="px-4 py-3 text-slate-600">{{ f.open_time }}–{{ f.close_time }}</td>
              <td class="px-4 py-3 text-center"><span :class="f.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="text-xs rounded-full px-2 py-0.5">{{ f.is_active ? 'Aktif' : 'Nonaktif' }}</span></td>
              <td class="px-4 py-3 text-right whitespace-nowrap">
                <button @click="openRates(f)" class="text-amber-600 text-sm hover:underline mr-3">Tarif</button>
                <button @click="openFac(f)" class="text-brand-600 text-sm hover:underline">Edit</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ===== COACHING ===== -->
    <div v-else-if="tab === 'coaching'">
      <!-- penegasan venue: coach & tarif SELALU milik venue yang dipilih di atas -->
      <div class="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5 mb-4 text-sm text-amber-800">
        Coach &amp; tarif di bawah ini berlaku untuk venue
        <b>{{ currentVenue ? currentVenue.code + ' — ' + currentVenue.name : '—' }}</b>.
        <span v-if="!isManager">Ganti venue di pemilih kanan atas kalau bukan venue ini.</span>
      </div>

      <!-- Tarif coaching -->
      <div class="bg-white rounded-xl shadow-sm border p-5 mb-5">
        <h3 class="font-semibold text-slate-700 mb-1">Tarif Coaching</h3>
        <p class="text-xs text-slate-500 mb-4">Harga <b>per jam</b>, di luar sewa lapangan (sewa lapangan ditagih terpisah).</p>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
          <div>
            <label class="block text-xs text-slate-500 mb-1">Harga 1 peserta / jam</label>
            <input v-model.number="rateFormC.base_price" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Tambahan per peserta / jam</label>
            <input v-model.number="rateFormC.extra_person_price" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Maksimal peserta</label>
            <input v-model.number="rateFormC.max_persons" type="number" min="1" max="20" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
        </div>
        <div class="bg-slate-50 rounded-lg p-3 mb-4">
          <p class="text-xs text-slate-500 mb-1.5">Harga jadi seperti ini:</p>
          <div class="flex flex-wrap gap-x-4 gap-y-1">
            <span v-for="p in coachPricePreview" :key="p.n" class="text-xs text-slate-600">
              {{ p.n }} org: <b>{{ rupiah(p.price) }}</b>/jam
            </span>
          </div>
        </div>
        <button @click="saveCoachRate" :disabled="savingRateC" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-5 py-2 font-medium disabled:opacity-40">
          {{ savingRateC ? 'Menyimpan…' : 'Simpan Tarif' }}
        </button>
        <p v-if="!coachRate" class="text-xs text-amber-600 mt-2">Tarif belum diatur — coaching belum bisa dipakai di POS.</p>
      </div>

      <!-- Daftar coach -->
      <div class="flex items-center justify-between mb-3">
        <p class="text-sm text-slate-500">Coach yang bisa dipilih kasir saat booking.</p>
        <button @click="openCoach()" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Coach</button>
      </div>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-3 font-medium">Nama</th>
            <th class="px-4 py-3 font-medium">No HP</th>
            <th class="px-4 py-3 font-medium text-center">Status</th>
            <th class="px-4 py-3"></th>
          </tr></thead>
          <tbody>
            <tr v-if="!coaches.length"><td colspan="4" class="px-4 py-8 text-center text-slate-400">Belum ada coach. Tambahkan dulu supaya coaching muncul di POS.</td></tr>
            <tr v-for="c in coaches" :key="c.id" class="border-t">
              <td class="px-4 py-3 font-medium text-slate-700">{{ c.name }}</td>
              <td class="px-4 py-3 text-slate-500 font-mono text-xs">{{ c.phone || '—' }}</td>
              <td class="px-4 py-3 text-center">
                <span :class="c.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="text-xs rounded-full px-2 py-0.5">
                  {{ c.is_active ? 'Aktif' : 'Nonaktif' }}
                </span>
              </td>
              <td class="px-4 py-3 text-right whitespace-nowrap">
                <button @click="openCoach(c)" class="text-brand-600 text-xs hover:underline mr-3">Ubah</button>
                <button @click="delCoach(c)" class="text-red-500 text-xs hover:underline">Hapus</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ===== TIKET ===== -->
    <div v-else-if="tab === 'tiket'">
      <div class="flex justify-end mb-3"><button @click="openTk()" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Tiket</button></div>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-3 font-medium">Nama Tiket</th>
            <th class="px-4 py-3 font-medium text-right">Harga Weekday</th>
            <th class="px-4 py-3 font-medium text-right">Harga Weekend/Libur</th>
            <th class="px-4 py-3 font-medium text-center">Status</th><th class="px-4 py-3"></th>
          </tr></thead>
          <tbody>
            <tr v-if="!tickets.length"><td colspan="5" class="px-4 py-8 text-center text-slate-400">Belum ada tiket.</td></tr>
            <tr v-for="t in tickets" :key="t.id" class="border-t hover:bg-slate-50">
              <td class="px-4 py-3 font-medium text-slate-700">{{ t.name }}</td>
              <td class="px-4 py-3 text-right">{{ rupiah(t.price) }}</td>
              <td class="px-4 py-3 text-right">{{ t.weekend_price != null ? rupiah(t.weekend_price) : '— (= weekday)' }}</td>
              <td class="px-4 py-3 text-center"><span :class="t.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="text-xs rounded-full px-2 py-0.5">{{ t.is_active ? 'Aktif' : 'Nonaktif' }}</span></td>
              <td class="px-4 py-3 text-right"><button @click="openTk(t)" class="text-brand-600 text-sm hover:underline">Edit</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="text-xs text-slate-400 mt-2">Harga Weekend berlaku otomatis pada Sabtu, Minggu &amp; hari libur. Kosongkan bila sama dengan weekday.</p>
    </div>

    <!-- ===== HARI LIBUR ===== -->
    <div v-else-if="tab === 'libur'">
      <div class="bg-white rounded-xl shadow-sm border p-4 mb-4 flex flex-wrap items-end gap-2 max-w-xl">
        <div><label class="block text-xs text-slate-500 mb-1">Tanggal</label>
          <input v-model="holForm.date" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
        <div class="flex-1"><label class="block text-xs text-slate-500 mb-1">Keterangan</label>
          <input v-model="holForm.name" placeholder="mis. HUT RI" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
        <button @click="addHoliday" :disabled="savingHol" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-50">+ Tambah</button>
      </div>
      <p class="text-xs text-slate-400 mb-3">Daftar ini berlaku <b>global</b> untuk semua venue — tanggal di sini dihitung sebagai weekend (harga tiket weekend).</p>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden max-w-xl">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr><th class="px-4 py-2 font-medium">Tanggal</th><th class="px-4 py-2 font-medium">Keterangan</th><th class="px-4 py-2"></th></tr></thead>
          <tbody>
            <tr v-if="!holidays.length"><td colspan="3" class="px-4 py-6 text-center text-slate-400">Belum ada hari libur.</td></tr>
            <tr v-for="h in holidays" :key="h.id" class="border-t">
              <td class="px-4 py-2 text-slate-700">{{ h.date }}</td>
              <td class="px-4 py-2 text-slate-500">{{ h.name || '—' }}</td>
              <td class="px-4 py-2 text-right"><button @click="delHoliday(h)" class="text-red-500 text-xs hover:text-red-700">Hapus</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal Lapangan -->
    <div v-if="showFac" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-md rounded-2xl p-5">
        <div class="flex justify-between items-center mb-4"><h3 class="text-lg font-bold text-slate-800">{{ editingFac ? 'Edit Lapangan' : 'Lapangan Baru' }}</h3><button @click="showFac = false" class="text-slate-400 text-xl">✕</button></div>
        <div class="space-y-3">
          <input v-model="facForm.name" placeholder="Nama (mis. Lapangan A)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <input v-model="facForm.type" placeholder="Tipe (mis. futsal, padel)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <div v-if="editingFac">
            <input v-model.number="facForm.hourly_rate" type="number" placeholder="Tarif per jam (dasar)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
            <p class="text-xs text-slate-400 mt-1">Tarif dasar ini berlaku di jam yg tak diatur khusus — atur tarif per jam lewat tombol "Tarif".</p>
          </div>
          <p v-else class="text-xs text-slate-400">Tarif diatur lewat tombol "Tarif" setelah lapangan dibuat.</p>
          <div class="grid grid-cols-2 gap-2">
            <div><label class="text-xs text-slate-500">Buka</label><input v-model="facForm.open_time" type="time" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
            <div><label class="text-xs text-slate-500">Tutup</label><input v-model="facForm.close_time" type="time" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          </div>
          <label class="flex items-center gap-2 text-sm text-slate-600"><input v-model="facForm.is_active" type="checkbox" /> Aktif</label>
          <p v-if="facErr" class="text-sm text-red-600">{{ facErr }}</p>
          <button @click="saveFac" :disabled="savingFac" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">{{ savingFac ? 'Menyimpan…' : 'Simpan' }}</button>
        </div>
      </div>
    </div>

    <!-- Modal Tarif per Jam -->
    <div v-if="showRates" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-lg rounded-2xl p-5">
        <div class="flex justify-between items-center mb-1">
          <h3 class="text-lg font-bold text-slate-800">Tarif per Jam — {{ rateFac?.name }}</h3>
          <button @click="showRates = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <p class="text-xs text-slate-400 mb-4">Tarif dasar {{ rupiah(rateFac?.hourly_rate) }}/jam berlaku di luar rentang jam di bawah ini.</p>

        <div class="bg-slate-50 rounded-lg border overflow-hidden mb-4">
          <table class="w-full text-sm">
            <thead class="bg-slate-100 text-slate-500 text-left"><tr>
              <th class="px-3 py-2 font-medium">Hari</th>
              <th class="px-3 py-2 font-medium">Label</th>
              <th class="px-3 py-2 font-medium">Jam</th>
              <th class="px-3 py-2 font-medium text-right">Tarif/jam</th>
              <th class="px-3 py-2"></th>
            </tr></thead>
            <tbody>
              <tr v-if="!rateRules.length"><td colspan="5" class="px-3 py-5 text-center text-slate-400">Belum ada tarif khusus — semua jam pakai tarif dasar.</td></tr>
              <tr v-for="r in rateRules" :key="r.id" class="border-t">
                <td class="px-3 py-2"><span class="text-xs bg-brand-50 text-brand-700 rounded px-1.5 py-0.5">{{ DAY_LABELS[r.day_type] || r.day_type }}</span></td>
                <td class="px-3 py-2 text-slate-700">{{ r.label || '—' }}</td>
                <td class="px-3 py-2 text-slate-600">{{ r.start_time }}–{{ r.end_time }}</td>
                <td class="px-3 py-2 text-right">{{ rupiah(r.hourly_rate) }}</td>
                <td class="px-3 py-2 text-right"><button @click="delRateRule(r)" class="text-red-500 text-xs hover:text-red-700">Hapus</button></td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="text-sm font-medium text-slate-600 mb-2">Tambah tarif baru</p>
        <div class="grid grid-cols-2 gap-2 mb-2">
          <div class="col-span-2"><label class="text-xs text-slate-500">Hari berlaku</label>
            <select v-model="rateForm.day_type" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option value="weekday">Weekday (Senin–Jumat)</option>
              <option value="thursday">Kamis (khusus — override weekday)</option>
              <option value="saturday">Sabtu</option>
              <option value="sunday">Minggu</option>
              <option value="holiday">Hari Libur Nasional</option>
            </select>
          </div>
          <input v-model="rateForm.label" placeholder="Label (mis. Malam)" class="col-span-2 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <div><label class="text-xs text-slate-500">Mulai</label><input v-model="rateForm.start_time" type="time" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="text-xs text-slate-500">Selesai</label><input v-model="rateForm.end_time" type="time" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <input v-model.number="rateForm.hourly_rate" type="number" placeholder="Tarif per jam" class="col-span-2 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
        </div>
        <p class="text-xs text-slate-400 mb-2">Jam selesai boleh <b>00:00</b> kalau berlaku sampai tengah malam.</p>
        <p v-if="rateErr" class="text-sm text-red-600 mb-2">{{ rateErr }}</p>
        <button @click="addRateRule" :disabled="savingRate" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">{{ savingRate ? 'Menyimpan…' : '+ Tambah Tarif' }}</button>
      </div>
    </div>

    <!-- Modal Tiket -->
    <div v-if="showTk" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-md rounded-2xl p-5">
        <div class="flex justify-between items-center mb-4"><h3 class="text-lg font-bold text-slate-800">{{ editingTk ? 'Edit Tiket' : 'Tiket Baru' }}</h3><button @click="showTk = false" class="text-slate-400 text-xl">✕</button></div>
        <div class="space-y-3">
          <input v-model="tkForm.name" placeholder="Nama tiket (mis. Tiket Dewasa)" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <div class="grid grid-cols-2 gap-2">
            <div><label class="block text-xs text-slate-500 mb-1">Harga Weekday</label><input v-model.number="tkForm.price" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
            <div><label class="block text-xs text-slate-500 mb-1">Harga Weekend/Libur</label><input v-model.number="tkForm.weekend_price" type="number" placeholder="kosong = sama" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          </div>
          <label v-if="editingTk" class="flex items-center gap-2 text-sm text-slate-600"><input v-model="tkForm.is_active" type="checkbox" /> Aktif</label>
          <p v-if="tkErr" class="text-sm text-red-600">{{ tkErr }}</p>
          <button @click="saveTk" :disabled="savingTk" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">{{ savingTk ? 'Menyimpan…' : 'Simpan' }}</button>
        </div>
      </div>
    </div>

    <!-- Modal coach -->
    <div v-if="showCoach" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-sm rounded-2xl p-5">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-slate-800">{{ editingCoach ? 'Edit Coach' : 'Coach Baru' }}</h3>
          <button @click="showCoach = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <div class="space-y-3">
          <div>
            <label class="block text-xs text-slate-500 mb-1">Nama coach</label>
            <input v-model="coachForm.name" placeholder="mis. Coach Budi" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">No HP (opsional)</label>
            <input v-model="coachForm.phone" placeholder="08…" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <label class="flex items-center gap-2 text-sm text-slate-600"><input v-model="coachForm.is_active" type="checkbox" /> Aktif (muncul di POS)</label>
          <p v-if="coachErr" class="text-sm text-red-600">{{ coachErr }}</p>
          <button @click="saveCoach" :disabled="savingCoach" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">{{ savingCoach ? 'Menyimpan…' : 'Simpan' }}</button>
        </div>
      </div>
    </div>

    <div v-if="toast" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
