<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { usePosStore } from '../stores/pos'

const pos = usePosStore()
const emit = defineEmits(['close', 'added'])

const facilityId = ref(null)
const date = ref(new Date().toISOString().slice(0, 10))
const start = ref('')
const end = ref('')
const bookings = ref([])
const loadingBookings = ref(false)
const error = ref('')

onMounted(async () => {
  if (!pos.facilities.length) await pos.fetchFacilities().catch(() => {})
  if (pos.facilities.length) facilityId.value = pos.facilities[0].id
})

const facility = computed(() => pos.facilities.find((f) => f.id === facilityId.value))

const hours = computed(() => {
  const f = facility.value
  if (!f) return []
  const oh = parseInt(f.open_time?.slice(0, 2) || '8')
  const ch = parseInt(f.close_time?.slice(0, 2) || '23')
  const arr = []
  for (let h = oh; h <= ch; h++) arr.push(String(h).padStart(2, '0') + ':00')
  return arr
})

const durationHours = computed(() => {
  if (!start.value || !end.value) return 0
  return (parseInt(end.value) - parseInt(start.value))
})
const price = computed(() => Math.max(0, durationHours.value) * (facility.value?.hourly_rate || 0))

function overlaps(s, e) {
  return bookings.value.some((b) => b.start_time < e && b.end_time > s)
}

async function loadBookings() {
  if (!facilityId.value || !date.value) return
  loadingBookings.value = true
  try {
    bookings.value = await pos.fetchFacilityBookings(facilityId.value, date.value)
  } catch (_) {
    bookings.value = []
  } finally {
    loadingBookings.value = false
  }
}
watch([facilityId, date], loadBookings, { immediate: true })

function rupiah(n) {
  return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
}

function add() {
  error.value = ''
  if (!facility.value) return (error.value = 'Pilih lapangan.')
  if (!start.value || !end.value) return (error.value = 'Pilih jam mulai & selesai.')
  if (durationHours.value <= 0) return (error.value = 'Jam selesai harus setelah jam mulai.')
  if (overlaps(start.value, end.value)) return (error.value = 'Jadwal bentrok dengan booking lain.')
  pos.addBooking({
    facility_id: facility.value.id,
    name: `${facility.value.name} ${date.value} ${start.value}-${end.value}`,
    unit_price: facility.value.hourly_rate,
    quantity: durationHours.value,
    booking_date: date.value,
    start_time: start.value,
    end_time: end.value,
  })
  emit('added')
  emit('close')
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">Booking Lapangan</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <div v-if="!pos.facilities.length" class="text-center text-slate-400 py-6">
        Belum ada lapangan untuk venue ini.
      </div>

      <template v-else>
        <label class="block text-sm text-slate-600 mb-1">Lapangan</label>
        <select v-model="facilityId" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 mb-3 outline-none focus:border-brand-500">
          <option v-for="f in pos.facilities" :key="f.id" :value="f.id">
            {{ f.name }} — {{ rupiah(f.hourly_rate) }}/jam
          </option>
        </select>

        <label class="block text-sm text-slate-600 mb-1">Tanggal</label>
        <input v-model="date" type="date" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 mb-3 outline-none focus:border-brand-500" />

        <div class="grid grid-cols-2 gap-2 mb-3">
          <div>
            <label class="block text-sm text-slate-600 mb-1">Mulai</label>
            <select v-model="start" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-brand-500">
              <option value="">--</option>
              <option v-for="h in hours" :key="h" :value="h">{{ h }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm text-slate-600 mb-1">Selesai</label>
            <select v-model="end" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-brand-500">
              <option value="">--</option>
              <option v-for="h in hours" :key="h" :value="h">{{ h }}</option>
            </select>
          </div>
        </div>

        <!-- Jadwal terisi -->
        <div class="bg-slate-50 rounded-lg p-3 mb-3">
          <p class="text-xs font-medium text-slate-500 mb-1.5">Jadwal terisi ({{ date }})</p>
          <p v-if="loadingBookings" class="text-xs text-slate-400">Memuat…</p>
          <p v-else-if="!bookings.length" class="text-xs text-emerald-600">Kosong — semua jam tersedia ✅</p>
          <div v-else class="flex flex-wrap gap-1.5">
            <span v-for="b in bookings" :key="b.id" class="text-xs bg-red-100 text-red-700 rounded px-2 py-0.5">
              {{ b.start_time }}–{{ b.end_time }}
            </span>
          </div>
        </div>

        <div class="flex justify-between items-center mb-3">
          <span class="text-sm text-slate-500">{{ durationHours > 0 ? durationHours + ' jam' : '—' }}</span>
          <span class="text-xl font-bold text-brand-700">{{ rupiah(price) }}</span>
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
