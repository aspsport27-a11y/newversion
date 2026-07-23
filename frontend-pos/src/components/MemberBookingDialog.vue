<script setup>
import { ref, computed, onMounted } from 'vue'
import { usePosStore } from '../stores/pos'

const pos = usePosStore()
const emit = defineEmits(['close', 'created'])

const facilityId = ref(null)
const custName = ref('')
const custPhone = ref('')
// hari: 0=Senin .. 6=Minggu (samakan dgn Python weekday di backend)
const DAYS = [['Sen', 0], ['Sel', 1], ['Rab', 2], ['Kam', 3], ['Jum', 4], ['Sab', 5], ['Min', 6]]
const days = ref([])
const today = new Date().toISOString().slice(0, 10)
const in30 = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10)
const dateFrom = ref(today)
const dateTo = ref(in30)
const startH = ref(null)
const endH = ref(null)
const discType = ref('percent') // 'percent' | 'amount'
const discValue = ref(0)
const busy = ref(false)
const err = ref('')

onMounted(async () => {
  if (!pos.facilities.length) await pos.fetchFacilities().catch(() => {})
  if (pos.facilities.length) facilityId.value = pos.facilities[0].id
})

const facility = computed(() => pos.facilities.find((f) => f.id === facilityId.value))

// jam tutup 00:00 = jam ke-24 (sama pola BookingDialog)
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
function rupiah(n) { return 'Rp ' + Math.round(Number(n) || 0).toLocaleString('id-ID') }

function toggleDay(v) {
  const i = days.value.indexOf(v)
  if (i >= 0) days.value.splice(i, 1)
  else days.value.push(v)
}

// tarif per rentang jam (mirror facility_rate_for_hour backend, utk preview)
function rateForHour(f, h) {
  for (const r of f.rate_rules || []) {
    let sh = parseInt(r.start_time.slice(0, 2))
    let eh = parseInt(r.end_time.slice(0, 2))
    if (r.end_time === '00:00' || eh <= sh) eh += 24
    const hh = h >= sh ? h : h + 24
    if (hh >= sh && hh < eh) return Number(r.hourly_rate)
  }
  return Number(f.hourly_rate || 0)
}
const perSession = computed(() => {
  const f = facility.value
  if (!f || startH.value == null || endH.value == null || endH.value <= startH.value) return 0
  let t = 0
  for (let h = startH.value; h < endH.value; h++) t += rateForHour(f, h % 24)
  return t
})
// daftar tanggal yang akan dibooking (preview lokal, sama pola dgn backend:
// JS getDay Min=0..Sab=6 → py weekday Sen=0..Min=6). Ditampilkan sbg chip biar
// kasir langsung lihat & sadar kalau ada tanggal kurang sebelum konfirmasi.
const DAY_LBL = ['Min', 'Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab']
const estDatesList = computed(() => {
  if (!days.value.length || !dateFrom.value || !dateTo.value) return []
  const wd = new Set(days.value) // py weekday
  const out = []
  const from = new Date(dateFrom.value + 'T00:00:00')
  const to = new Date(dateTo.value + 'T00:00:00')
  for (let d = new Date(from); d <= to && out.length < 200; d.setDate(d.getDate() + 1)) {
    if (wd.has((d.getDay() + 6) % 7)) out.push(new Date(d))
  }
  return out
})
const estDates = computed(() => estDatesList.value.length)
function fmtChip(d) {
  return `${DAY_LBL[d.getDay()]} ${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`
}
const subtotal = computed(() => perSession.value * estDates.value)
const discountRp = computed(() => {
  if (discType.value === 'percent') return Math.round(subtotal.value * Math.min(Math.max(discValue.value || 0, 0), 100) / 100)
  return Math.max(0, discValue.value || 0)
})
const grandTotal = computed(() => Math.max(0, subtotal.value - Math.min(discountRp.value, subtotal.value)))

async function submit() {
  err.value = ''
  if (!facility.value) return (err.value = 'Pilih lapangan.')
  if (!days.value.length) return (err.value = 'Pilih minimal 1 hari.')
  if (startH.value == null || endH.value == null || endH.value <= startH.value) return (err.value = 'Pilih jam mulai & selesai yang benar.')
  busy.value = true
  try {
    const data = await pos.createMemberBooking({
      facility_id: facility.value.id,
      weekdays: days.value,
      date_from: dateFrom.value,
      date_to: dateTo.value,
      start_time: hhmm(startH.value),
      end_time: hhmm(endH.value),
      discount_type: discType.value,
      discount_value: Number(discValue.value) || 0,
      customer_name: custName.value || null,
      customer_phone: custPhone.value || null,
    })
    // teruskan order yg sudah dibuat + info tanggal dilewati ke parent utk dibayar
    emit('created', { order: data.order, booked: data.booked_dates, skipped: data.skipped_dates })
  } catch (e) {
    err.value = e?.response?.data?.message || 'Gagal membuat booking member.'
  } finally { busy.value = false }
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">🗓️ Booking Member</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <div v-if="!pos.facilities.length" class="text-center text-slate-400 py-6">Belum ada lapangan untuk venue ini.</div>

      <template v-else>
        <div class="grid grid-cols-2 gap-2 mb-3">
          <div>
            <label class="block text-sm text-slate-600 mb-1">Nama Member</label>
            <input v-model="custName" placeholder="Nama" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500" />
          </div>
          <div>
            <label class="block text-sm text-slate-600 mb-1">No. HP</label>
            <input v-model="custPhone" placeholder="opsional" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500" />
          </div>
        </div>

        <label class="block text-sm text-slate-600 mb-1">Lapangan</label>
        <select v-model="facilityId" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 mb-3 outline-none focus:border-brand-500">
          <option v-for="f in pos.facilities" :key="f.id" :value="f.id">{{ f.name }}</option>
        </select>

        <label class="block text-sm text-slate-600 mb-1">Hari main (berulang tiap minggu)</label>
        <div class="flex gap-1.5 mb-3 flex-wrap">
          <button v-for="[lbl, v] in DAYS" :key="v" @click="toggleDay(v)" type="button"
            :class="days.includes(v) ? 'bg-brand-600 text-white border-brand-600' : 'bg-white text-slate-600 border-slate-300'"
            class="px-3 py-1.5 rounded-lg border text-sm font-medium">{{ lbl }}</button>
        </div>

        <div class="grid grid-cols-2 gap-2 mb-3">
          <div>
            <label class="block text-sm text-slate-600 mb-1">Dari tanggal</label>
            <input v-model="dateFrom" type="date" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500" />
          </div>
          <div>
            <label class="block text-sm text-slate-600 mb-1">Sampai tanggal</label>
            <input v-model="dateTo" type="date" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500" />
          </div>
        </div>

        <div class="grid grid-cols-2 gap-2 mb-3">
          <div>
            <label class="block text-sm text-slate-600 mb-1">Jam mulai</label>
            <select v-model.number="startH" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500">
              <option :value="null">--</option>
              <option v-for="h in hours" :key="h" :value="h">{{ hhmm(h) }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm text-slate-600 mb-1">Jam selesai</label>
            <select v-model.number="endH" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500">
              <option :value="null">--</option>
              <option v-for="h in hours" :key="h" :value="h">{{ hhmm(h) }}</option>
            </select>
          </div>
        </div>

        <label class="block text-sm text-slate-600 mb-1">Diskon member</label>
        <div class="flex gap-2 mb-3">
          <div class="flex rounded-lg border border-slate-300 overflow-hidden">
            <button @click="discType = 'percent'" type="button" :class="discType === 'percent' ? 'bg-brand-600 text-white' : 'bg-white text-slate-600'" class="px-3 text-sm font-medium">%</button>
            <button @click="discType = 'amount'" type="button" :class="discType === 'amount' ? 'bg-brand-600 text-white' : 'bg-white text-slate-600'" class="px-3 text-sm font-medium">Rp</button>
          </div>
          <input v-model.number="discValue" type="number" min="0" :placeholder="discType === 'percent' ? '0 %' : '0 rupiah'" class="flex-1 rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-right outline-none focus:border-brand-500" />
        </div>

        <div class="bg-slate-50 rounded-lg p-3 mb-3 text-sm space-y-1">
          <div v-if="estDatesList.length" class="mb-1">
            <p class="text-xs text-slate-500 mb-1">{{ estDatesList.length }} tanggal akan dibooking:</p>
            <div class="flex flex-wrap gap-1">
              <span v-for="(d, i) in estDatesList" :key="i" class="text-xs bg-white border border-slate-200 rounded px-1.5 py-0.5 text-slate-600">{{ fmtChip(d) }}</span>
            </div>
          </div>
          <div class="flex justify-between"><span class="text-slate-500">{{ estDates }} sesi × {{ rupiah(perSession) }}</span><span>{{ rupiah(subtotal) }}</span></div>
          <div v-if="discountRp > 0" class="flex justify-between text-amber-600"><span>Diskon</span><span>− {{ rupiah(discountRp) }}</span></div>
          <div class="flex justify-between font-bold text-base border-t pt-1.5"><span>Perkiraan total</span><span class="text-brand-700">{{ rupiah(grandTotal) }}</span></div>
          <p class="text-xs text-slate-400 pt-1">Tanggal yang bentrok booking lain akan dilewati otomatis. Total final dihitung server.</p>
        </div>

        <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">{{ err }}</p>

        <button @click="submit" :disabled="busy || !estDates"
          class="w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-semibold disabled:opacity-40">
          {{ busy ? 'Memproses…' : 'Buat Booking Member & Bayar' }}
        </button>
      </template>
    </div>
  </div>
</template>
