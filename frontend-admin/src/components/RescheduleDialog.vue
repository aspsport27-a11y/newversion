<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import client from '../api/client'
import { bookingPrice, dayTypeFor } from '../utils/bookingPrice'

// order = detail order (punya id, venue_id, items[], amount_paid, customer_name)
const props = defineProps({ order: Object, venueId: Number })
const emit = defineEmits(['close', 'done'])

const bookingItems = computed(() => (props.order?.items || []).filter((i) => i.item_type === 'booking'))
const itemId = ref(null)
const facilities = ref([])
const holidays = ref([])
const facilityId = ref(null)
const date = ref(new Date().toISOString().slice(0, 10))
const startH = ref(null)
const endH = ref(null)
const busy = ref(false)
const err = ref('')

const vid = computed(() => props.venueId || props.order?.venue_id)

onMounted(async () => {
  itemId.value = bookingItems.value[0]?.id ?? null
  try {
    const [f, h] = await Promise.all([
      client.get('/admin/facilities', { params: { venue_id: vid.value } }),
      client.get('/admin/holidays').catch(() => ({ data: { holidays: [] } })),
    ])
    facilities.value = f.data.facilities || []
    holidays.value = (h.data.holidays || []).map((x) => x.date)
    facilityId.value = facilities.value[0]?.id ?? null
    coachId.value = bookingInfo.value?.coach_id ?? null
    await loadCoaches()
  } catch (e) {
    err.value = 'Gagal memuat lapangan.'
  }
})

const facility = computed(() => facilities.value.find((f) => f.id === facilityId.value))
const selectedItem = computed(() => bookingItems.value.find((i) => i.id === itemId.value))

// ---------- coaching: bisa sekalian GANTI COACH ----------
// Coach menempel di SLOT (bukan order_item), jadi info-nya datang dari
// order.bookings yg dikirim endpoint detail.
const bookingInfo = computed(() =>
  (props.order?.bookings || []).find((b) => b.order_item_id === itemId.value),
)
const hasCoaching = computed(() => !!bookingInfo.value?.coach_id)
const coaches = ref([])
const coachId = ref(null)
const coachOverride = ref(false)

// muat ulang status coach tiap slot tujuan berubah — 'available'/'declared'
// dihitung server utk slot itu (slot ini sendiri dikecualikan dr cek bentrok)
async function loadCoaches() {
  if (!hasCoaching.value) { coaches.value = []; return }
  const params = { venue_id: vid.value }
  if (date.value && startH.value != null && endH.value != null && durationHours.value > 0) {
    params.date = date.value
    params.start_time = hhmm(startH.value)
    params.end_time = hhmm(endH.value)
    if (bookingInfo.value?.booking_id) params.exclude_booking_id = bookingInfo.value.booking_id
  }
  try {
    const { data } = await client.get('/admin/coaches', { params })
    coaches.value = (data.coaches || []).filter((c) => c.is_active)
  } catch (_) { coaches.value = [] }
}
watch([itemId, date, startH, endH], async () => {
  coachOverride.value = false
  if (coachId.value == null) coachId.value = bookingInfo.value?.coach_id ?? null
  await loadCoaches()
})
// coach yg sedang mengajar di slot tujuan disembunyikan (bentrok nyata)
const pilihanCoach = computed(() => coaches.value.filter((c) => c.available !== false))
const coachTerpilih = computed(() => coaches.value.find((c) => c.id === coachId.value))
const perluKonfirmasi = computed(() => !!coachTerpilih.value && coachTerpilih.value.declared === false)
const gantiCoach = computed(() => hasCoaching.value && coachId.value !== bookingInfo.value?.coach_id)

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
function hhmm(h) { return String(h % 24).padStart(2, '0') + ':00' }
function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }

const durationHours = computed(() => (startH.value != null && endH.value != null ? endH.value - startH.value : 0))
const oldLine = computed(() => Number(selectedItem.value?.line_total || 0))
const newPrice = computed(() => {
  if (!facility.value || durationHours.value <= 0) return 0
  return bookingPrice(facility.value, startH.value, endH.value, dayTypeFor(date.value, holidays.value))
})
// total order baru = total lama − harga slot lama + harga slot baru
const newOrderTotal = computed(() => Number(props.order?.total_amount || 0) - oldLine.value + newPrice.value)
const paid = computed(() => Number(props.order?.amount_paid || 0))
// >0 tagih ke customer (jadi partial); <0 kelebihan → refund kas keluar
const diff = computed(() => newOrderTotal.value - paid.value)

async function submit() {
  err.value = ''
  if (!selectedItem.value) return (err.value = 'Pilih slot yang direschedule.')
  if (!facilityId.value) return (err.value = 'Pilih lapangan tujuan.')
  if (durationHours.value <= 0) return (err.value = 'Jam selesai harus setelah jam mulai.')
  if (hasCoaching.value && !coachId.value) return (err.value = 'Pilih coach.')
  if (perluKonfirmasi.value && !coachOverride.value)
    return (err.value = 'Coach di luar jam ketersediaannya — centang konfirmasi dulu.')
  busy.value = true
  try {
    const { data } = await client.post(`/admin/orders/${props.order.id}/reschedule`, {
      order_item_id: itemId.value, facility_id: facilityId.value,
      booking_date: date.value, start_time: hhmm(startH.value), end_time: hhmm(endH.value),
      ...(hasCoaching.value
        ? { coach_id: coachId.value, ...(perluKonfirmasi.value ? { coach_override: true } : {}) }
        : {}),
    })
    emit('done', data)
  } catch (e) {
    err.value = e?.response?.data?.message || 'Gagal reschedule.'
  } finally { busy.value = false }
}
</script>

<template>
  <div class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" @click.self="emit('close')">
    <div class="bg-white w-full max-w-md rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">📅 Reschedule Booking</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <p class="text-sm text-slate-600 mb-1">Customer: <b>{{ order.customer_name || 'Tanpa nama' }}</b></p>

      <label class="block text-xs text-slate-500 mb-1 mt-3">Slot sekarang</label>
      <select v-if="bookingItems.length > 1" v-model="itemId" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm mb-3">
        <option v-for="it in bookingItems" :key="it.id" :value="it.id">{{ it.name }}</option>
      </select>
      <p v-else class="text-sm text-slate-700 bg-slate-50 rounded-lg px-3 py-2 mb-3">{{ selectedItem?.name || '—' }}</p>

      <label class="block text-xs text-slate-500 mb-1">Pindah ke — Lapangan</label>
      <select v-model="facilityId" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 mb-3 outline-none focus:border-brand-500">
        <option v-for="f in facilities" :key="f.id" :value="f.id">{{ f.name }}</option>
      </select>

      <label class="block text-xs text-slate-500 mb-1">Tanggal</label>
      <input v-model="date" type="date" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 mb-3 outline-none focus:border-brand-500" />

      <div class="grid grid-cols-2 gap-2 mb-3">
        <div>
          <label class="block text-xs text-slate-500 mb-1">Mulai</label>
          <select v-model.number="startH" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-brand-500">
            <option :value="null">--</option>
            <option v-for="h in hours" :key="h" :value="h">{{ hhmm(h) }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs text-slate-500 mb-1">Selesai</label>
          <select v-model.number="endH" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-brand-500">
            <option :value="null">--</option>
            <option v-for="h in hours" :key="h" :value="h">{{ hhmm(h) }}</option>
          </select>
        </div>
      </div>

      <!-- Coaching: bisa sekalian ganti coach -->
      <div v-if="hasCoaching" class="border border-teal-200 bg-teal-50/50 rounded-lg p-3 mb-3">
        <label class="block text-xs text-slate-500 mb-1">
          Coach <span class="text-slate-400">(bisa diganti kalau coach lama berhalangan)</span>
        </label>
        <select v-model.number="coachId" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500">
          <option :value="null">-- pilih coach --</option>
          <option v-for="c in pilihanCoach" :key="c.id" :value="c.id">
            {{ c.name }}{{ c.declared === false ? ' — di luar jam tersedia' : '' }}
          </option>
        </select>
        <p v-if="gantiCoach" class="text-xs text-teal-700 mt-1">
          Coach diganti dari <b>{{ bookingInfo?.coach_name || '—' }}</b> ke <b>{{ coachTerpilih?.name }}</b>.
        </p>
        <p v-if="durationHours > 0 && !pilihanCoach.length" class="text-xs text-amber-600 mt-1">
          Semua coach sudah mengajar di jam tujuan.
        </p>
        <label v-if="perluKonfirmasi" class="mt-2 flex items-start gap-2 bg-amber-50 border border-amber-300 rounded-lg p-2.5 cursor-pointer">
          <input type="checkbox" v-model="coachOverride" class="w-4 h-4 mt-0.5 accent-amber-600 shrink-0" />
          <span class="text-xs text-amber-800">
            <b>{{ coachTerpilih?.name }}</b> tidak menyatakan diri tersedia di jam tujuan.
            Saya sudah memastikan coach bersedia.
          </span>
        </label>
        <p class="text-[11px] text-slate-400 mt-1.5">
          Jumlah peserta tetap {{ bookingInfo?.coaching_persons || 1 }} orang — biaya coaching menyesuaikan durasi baru.
        </p>
      </div>

      <div v-if="durationHours > 0" class="bg-slate-50 rounded-lg p-3 text-sm space-y-1 mb-3">
        <div class="flex justify-between"><span class="text-slate-500">Harga slot baru</span><span class="font-medium">{{ rupiah(newPrice) }}</span></div>
        <div class="flex justify-between"><span class="text-slate-500">Sudah dibayar</span><span>-{{ rupiah(paid) }}</span></div>
        <div class="flex justify-between font-bold border-t pt-1">
          <span>{{ diff >= 0 ? 'Tagih ke customer' : 'Kembalikan (kas keluar)' }}</span>
          <span :class="diff >= 0 ? 'text-amber-600' : 'text-emerald-600'">{{ rupiah(Math.abs(diff)) }}</span>
        </div>
        <p v-if="diff < 0" class="text-[11px] text-slate-400 pt-1">Kelebihan dicatat otomatis sebagai kas keluar di shift kasir yang terbuka di venue ini.</p>
      </div>

      <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">{{ err }}</p>

      <button @click="submit" :disabled="busy || durationHours <= 0"
        class="w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-semibold disabled:opacity-40">
        {{ busy ? 'Memproses…' : 'Konfirmasi Reschedule' }}
      </button>
    </div>
  </div>
</template>
