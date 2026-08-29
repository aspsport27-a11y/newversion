<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { usePosStore } from '../stores/pos'
import { dayTypeFor, bookingPrice } from '../utils/bookingPrice'

const pos = usePosStore()
const emit = defineEmits(['close', 'added'])

const facilityId = ref(null)
const date = ref(new Date().toISOString().slice(0, 10))
// disimpan sbg jam angka (bukan string) supaya tutup tengah malam (00:00 = jam ke-24)
// tak salah dibandingkan sbg "lebih kecil" dari jam buka — lihat hours/hhmm di bawah
const startH = ref(null)
const endH = ref(null)
const bookings = ref([])
const events = ref([])
const loadingBookings = ref(false)
const error = ref('')

onMounted(async () => {
  if (!pos.facilities.length) await pos.fetchFacilities().catch(() => {})
  if (pos.facilities.length) facilityId.value = pos.facilities[0].id
})

const facility = computed(() => pos.facilities.find((f) => f.id === facilityId.value))

// venue padel: pakai istilah "Court" & tak menampilkan rincian tarif
const isPadel = computed(() => (pos.venue?.type || '').toLowerCase() === 'padel')
const unitTerm = computed(() => (isPadel.value ? 'Court' : 'Lapangan'))

// jam tutup "00:00" berarti tengah malam (akhir hari), bukan awal hari — diperlakukan
// sbg jam ke-24 supaya urutan jam tetap benar (mis. buka 08:00 tutup 00:00 → 08..24)
const hours = computed(() => {
  const f = facility.value
  if (!f) return []
  const oh = parseInt(f.open_time?.slice(0, 2) ?? '8')
  let ch = parseInt(f.close_time?.slice(0, 2) ?? '23')
  if (ch <= oh) ch += 24
  const arr = []
  for (let h = oh; h <= ch; h++) arr.push(h)
  return arr
})
function hhmm(h) {
  return String(h % 24).padStart(2, '0') + ':00'
}
function toMinutes(hhmmStr) {
  const [h, m] = hhmmStr.split(':').map(Number)
  return h * 60 + (m || 0)
}

const durationHours = computed(() => {
  if (startH.value == null || endH.value == null) return 0
  return endH.value - startH.value
})

// Kategori hari + hitung tarif dari util bersama (utils/bookingPrice.js) —
// cermin facility_rate_for_hour() backend. Termasuk override khusus Kamis.
const dayType = computed(() => dayTypeFor(date.value, pos.holidays))
const price = computed(() => {
  const f = facility.value
  if (!f || durationHours.value <= 0) return 0
  return bookingPrice(f, startH.value, endH.value, dayType.value)
})

// ---------- coaching (padel) ----------
// UI coaching cuma muncul kalau venue ini punya coach terdaftar & tarifnya
// sudah diatur — venue lain (futsal/waterpark/dll) sama sekali tak berubah.
const coaches = ref([])
const coachingRate = ref(null)
const useCoaching = ref(false)
const coachId = ref(null)
const persons = ref(1)
const hasCoaching = computed(() => coaches.value.length > 0 && coachingRate.value != null)
const maxPersons = computed(() => coachingRate.value?.max_persons || 4)

async function loadCoaching() {
  const params = {}
  // kirim slot terpilih supaya server tandai coach yang sudah mengajar di jam itu
  if (date.value && startH.value != null && endH.value != null && durationHours.value > 0) {
    params.date = date.value
    params.start_time = hhmm(startH.value)
    params.end_time = hhmm(endH.value)
  }
  try {
    const d = await pos.fetchCoaching(params)
    coaches.value = d.coaches || []
    coachingRate.value = d.rate || null
    // coach yang dipilih ternyata sudah tak tersedia di slot baru → lepas
    if (coachId.value && !coaches.value.some((c) => c.id === coachId.value && c.available)) {
      coachId.value = null
    }
  } catch (_) {
    coaches.value = []
    coachingRate.value = null
  }
}
onMounted(loadCoaching)
watch([date, startH, endH], loadCoaching)

// coach yg sedang mengajar (available=false) benar-benar bentrok → disembunyikan.
// coach di luar jam ketersediaannya (declared=false) TETAP muncul, ditandai,
// tapi kasir harus konfirmasi dulu.
const availableCoaches = computed(() => coaches.value.filter((c) => c.available))
const selectedCoach = computed(() => coaches.value.find((c) => c.id === coachId.value))
const needsOverride = computed(() => !!selectedCoach.value && selectedCoach.value.declared === false)
const coachOverride = ref(false)
watch([coachId, startH, endH, date], () => { coachOverride.value = false })
const coachingPerHour = computed(() => {
  const r = coachingRate.value
  if (!r) return 0
  return Number(r.base_price) + (Math.max(1, persons.value) - 1) * Number(r.extra_person_price)
})
const coachingTotal = computed(() =>
  useCoaching.value && coachId.value && durationHours.value > 0
    ? coachingPerHour.value * durationHours.value
    : 0,
)
const grandTotal = computed(() => price.value + coachingTotal.value)

function overlaps(sH, eH) {
  const sMin = sH * 60
  const eMin = eH * 60
  const hit = (rows) => rows.some((b) => {
    const bs = toMinutes(b.start_time)
    let be = toMinutes(b.end_time)
    if (be <= bs) be += 24 * 60 // rentang yg juga berakhir tengah malam
    return bs < eMin && be > sMin
  })
  return hit(bookings.value) || hit(events.value)
}

async function loadBookings() {
  if (!facilityId.value || !date.value) return
  loadingBookings.value = true
  try {
    const data = await pos.fetchFacilityBookings(facilityId.value, date.value)
    bookings.value = data.bookings || []
    events.value = data.events || []
  } catch (_) {
    bookings.value = []; events.value = []
  } finally {
    loadingBookings.value = false
  }
}
watch([facilityId, date], loadBookings, { immediate: true })

function rupiah(n) {
  return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
}

// label ringkas tarif utk dropdown/info — kalau ada rate_rules, tarif flat
// dasar sering tak relevan lagi (bisa 0), jadi tampilkan rentang tarif
function facilityRateLabel(f) {
  const rates = (f.rate_rules || []).map((r) => Number(r.hourly_rate))
  if (f.hourly_rate) rates.push(Number(f.hourly_rate))
  if (!rates.length) return rupiah(0) + '/jam'
  const min = Math.min(...rates)
  const max = Math.max(...rates)
  return min === max ? `${rupiah(min)}/jam` : `${rupiah(min)}–${rupiah(max)}/jam`
}

function add() {
  error.value = ''
  if (!facility.value) return (error.value = `Pilih ${unitTerm.value.toLowerCase()}.`)
  if (!(pos.customerPhone || '').trim()) return (error.value = 'No. HP customer wajib diisi untuk booking.')
  if (startH.value == null || endH.value == null) return (error.value = 'Pilih jam mulai & selesai.')
  if (durationHours.value <= 0) return (error.value = 'Jam selesai harus setelah jam mulai.')
  if (overlaps(startH.value, endH.value)) return (error.value = 'Jadwal bentrok dengan booking lain.')
  if (useCoaching.value && !coachId.value) return (error.value = 'Pilih coach untuk coaching.')
  if (useCoaching.value && needsOverride.value && !coachOverride.value)
    return (error.value = 'Coach ini di luar jam ketersediaannya — centang konfirmasi dulu.')
  const startStr = hhmm(startH.value)
  const endStr = hhmm(endH.value)
  const withCoach = useCoaching.value && coachId.value
  pos.addBooking({
    facility_id: facility.value.id,
    name: `${facility.value.name} ${date.value} ${startStr}-${endStr}`,
    // dikirim tarif rata2/jam (blended) hanya utk TAMPILAN; total baris pakai
    // line_total EKSAK (jumlah tarif per jam) supaya tak meleset 1 rupiah dari
    // server (server tetap hitung ulang pakai facility_rate_for_hour).
    unit_price: Math.round(price.value / durationHours.value),
    quantity: durationHours.value,
    line_total: price.value,
    booking_date: date.value,
    start_time: startStr,
    end_time: endStr,
    // coaching: server yg bikin baris uang & harga finalnya
    ...(withCoach
      ? {
          coach_id: coachId.value,
          coaching_persons: persons.value,
          ...(needsOverride.value ? { coach_override: true } : {}),
        }
      : {}),
    coaching_label: withCoach
      ? `Coaching ${persons.value} org (${coaches.value.find((c) => c.id === coachId.value)?.name || ''})`
      : null,
    coaching_preview: withCoach ? coachingTotal.value : 0,
  })
  emit('added')
  emit('close')
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">Booking {{ unitTerm }}</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <div v-if="!pos.facilities.length" class="text-center text-slate-400 py-6">
        Belum ada {{ unitTerm.toLowerCase() }} untuk venue ini.
      </div>

      <template v-else>
        <div class="grid grid-cols-2 gap-2 mb-3">
          <div>
            <label class="block text-sm text-slate-600 mb-1">Nama Customer</label>
            <input v-model="pos.customerName" placeholder="Nama pemesan" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500" />
          </div>
          <div>
            <label class="block text-sm text-slate-600 mb-1">No. HP <span class="text-red-500">*</span></label>
            <input v-model="pos.customerPhone" placeholder="wajib" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500" />
          </div>
        </div>

        <label class="block text-sm text-slate-600 mb-1">{{ unitTerm }}</label>
        <select v-model="facilityId" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 mb-1 outline-none focus:border-brand-500">
          <option v-for="f in pos.facilities" :key="f.id" :value="f.id">
            {{ f.name }}<span v-if="!isPadel"> — {{ facilityRateLabel(f) }}</span>
          </option>
        </select>
        <div class="mb-3"></div>

        <label class="block text-sm text-slate-600 mb-1">Tanggal</label>
        <input v-model="date" type="date" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 mb-3 outline-none focus:border-brand-500" />

        <div class="grid grid-cols-2 gap-2 mb-3">
          <div>
            <label class="block text-sm text-slate-600 mb-1">Mulai</label>
            <select v-model.number="startH" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-brand-500">
              <option :value="null">--</option>
              <option v-for="h in hours" :key="h" :value="h">{{ hhmm(h) }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm text-slate-600 mb-1">Selesai</label>
            <select v-model.number="endH" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-brand-500">
              <option :value="null">--</option>
              <option v-for="h in hours" :key="h" :value="h">{{ hhmm(h) }}</option>
            </select>
          </div>
        </div>

        <!-- Jadwal terisi -->
        <div class="bg-slate-50 rounded-lg p-3 mb-3">
          <p class="text-xs font-medium text-slate-500 mb-1.5">Jadwal terisi ({{ date }})</p>
          <p v-if="loadingBookings" class="text-xs text-slate-400">Memuat…</p>
          <p v-else-if="!bookings.length && !events.length" class="text-xs text-emerald-600">Kosong — semua jam tersedia ✅</p>
          <div v-else class="flex flex-wrap gap-1.5">
            <span v-for="(e, i) in events" :key="'ev'+i" class="text-xs bg-rose-100 text-rose-700 rounded px-2 py-0.5 font-medium">
              🏆 {{ e.start_time }}–{{ e.end_time }} {{ e.name }}
            </span>
            <span v-for="b in bookings" :key="b.id" class="text-xs bg-red-100 text-red-700 rounded px-2 py-0.5">
              {{ b.start_time }}–{{ b.end_time }}
            </span>
          </div>
        </div>

        <!-- Coaching (hanya venue yg punya coach & tarifnya sudah diatur) -->
        <div v-if="hasCoaching" class="border border-teal-200 bg-teal-50/50 rounded-lg p-3 mb-3">
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" v-model="useCoaching" class="w-4 h-4 accent-teal-600" />
            <span class="text-sm font-medium text-slate-700">Pakai Coach (coaching)</span>
          </label>

          <div v-if="useCoaching" class="mt-3 space-y-2">
            <div>
              <label class="block text-xs text-slate-500 mb-1">Coach</label>
              <select v-model.number="coachId" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500">
                <option :value="null">-- pilih coach --</option>
                <option v-for="c in availableCoaches" :key="c.id" :value="c.id">
                  {{ c.name }}{{ c.declared === false ? ' — di luar jam tersedia' : '' }}
                </option>
              </select>
              <!-- coach boleh dipakai di luar jamnya, tapi harus dikonfirmasi -->
              <label v-if="needsOverride" class="mt-2 flex items-start gap-2 bg-amber-50 border border-amber-300 rounded-lg p-2.5 cursor-pointer">
                <input type="checkbox" v-model="coachOverride" class="w-4 h-4 mt-0.5 accent-amber-600 shrink-0" />
                <span class="text-xs text-amber-800">
                  <b>{{ selectedCoach?.name }}</b> tidak menyatakan diri tersedia di jam ini.
                  Saya sudah memastikan coach bersedia.
                </span>
              </label>
              <p v-if="durationHours > 0 && !availableCoaches.length" class="text-xs text-amber-600 mt-1">
                Semua coach sudah mengajar di jam ini.
              </p>
              <p v-else-if="durationHours <= 0" class="text-xs text-slate-400 mt-1">
                Pilih jam dulu untuk melihat coach yang tersedia.
              </p>
            </div>
            <div>
              <label class="block text-xs text-slate-500 mb-1">Jumlah peserta (maks {{ maxPersons }})</label>
              <select v-model.number="persons" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500">
                <option v-for="n in maxPersons" :key="n" :value="n">{{ n }} orang</option>
              </select>
            </div>
            <p class="text-xs text-slate-500">
              Tarif coaching {{ rupiah(coachingPerHour) }}/jam · di luar sewa {{ unitTerm.toLowerCase() }}
            </p>
          </div>
        </div>

        <!-- Ringkasan harga -->
        <div class="border-t pt-3 mb-3">
          <div v-if="coachingTotal > 0" class="space-y-1 mb-2">
            <div class="flex justify-between text-sm">
              <span class="text-slate-500">Sewa {{ unitTerm.toLowerCase() }} {{ durationHours }} jam</span>
              <span class="text-slate-700">{{ rupiah(price) }}</span>
            </div>
            <div class="flex justify-between text-sm">
              <span class="text-slate-500">Coaching {{ persons }} org × {{ durationHours }} jam</span>
              <span class="text-slate-700">{{ rupiah(coachingTotal) }}</span>
            </div>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm text-slate-500">{{ durationHours > 0 ? durationHours + ' jam' : '—' }}</span>
            <span class="text-xl font-bold text-brand-700">{{ rupiah(grandTotal) }}</span>
          </div>
        </div>

        <p v-if="error" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">{{ error }}</p>

        <button @click="add" :disabled="price <= 0"
          class="w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-semibold disabled:opacity-40">
          Tambah ke Keranjang
        </button>
      </template>
    </div>
  </div>
</template>
