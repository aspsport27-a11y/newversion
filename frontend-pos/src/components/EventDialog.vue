<script setup>
import { ref, computed, watch } from 'vue'
import { usePosStore } from '../stores/pos'
import PaymentDialog from './PaymentDialog.vue'
import RescheduleDialog from './RescheduleDialog.vue'

const pos = usePosStore()
const emit = defineEmits(['close', 'done'])

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
const today = new Date().toISOString().slice(0, 10)

const phase = ref('form')            // form | pay | result
const err = ref('')
const form = ref({
  name: '', renter: '', phone: '',
  date_from: today, date_to: today,
  start_time: '08:00', end_time: '17:00',
  price: null,
})
const quote = ref({ suggested_price: 0, facility_count: 0, conflict_count: 0, conflicts: [] })
const quoting = ref(false)
let quoteTimer = null

// --- pilihan lapangan ---
const facilities = ref([])          // [{id,name}] lapangan venue
const selectedFac = ref(null)       // Set id terpilih; null = belum di-load
const allSelected = computed(() => facilities.value.length > 0 && selectedFac.value && selectedFac.value.size === facilities.value.length)
function facSelected(id) { return selectedFac.value ? selectedFac.value.has(id) : false }
function toggleFac(id) {
  const s = new Set(selectedFac.value || [])
  s.has(id) ? s.delete(id) : s.add(id)
  selectedFac.value = s
  refreshQuote()
}
function selectAllFac() { selectedFac.value = new Set(facilities.value.map((f) => f.id)); refreshQuote() }
// param facility_ids utk quote (CSV) & create (array) — null bila SEMUA terpilih (=borong)
function facIdsParam() {
  if (!selectedFac.value || allSelected.value) return null
  return [...selectedFac.value]
}

function formValid() {
  const f = form.value
  return f.name.trim() && f.date_from && f.date_to && f.date_to >= f.date_from &&
    f.start_time && f.end_time && f.end_time > f.start_time
}
// jumlah lapangan & harga usulan hanya butuh tanggal+jam — jangan syaratkan nama
function quoteValid() {
  const f = form.value
  return f.date_from && f.date_to && f.date_to >= f.date_from &&
    f.start_time && f.end_time && f.end_time > f.start_time
}

async function refreshQuote() {
  if (!quoteValid()) return
  quoting.value = true
  try {
    const ids = facIdsParam()
    const q = await pos.eventQuote({
      date_from: form.value.date_from, date_to: form.value.date_to,
      start_time: form.value.start_time, end_time: form.value.end_time,
      ...(ids ? { facility_ids: ids.join(',') } : {}),
    })
    // isi daftar lapangan sekali; default SEMUA terpilih (borong)
    if (q.facilities && !facilities.value.length) {
      facilities.value = q.facilities
      if (!selectedFac.value) selectedFac.value = new Set(q.facilities.map((f) => f.id))
    }
    quote.value = q
    // isi harga usulan jika kasir belum mengubahnya manual
    if (form.value.price === null || form.value.price === '') form.value.price = q.suggested_price
  } catch { /* diamkan */ } finally { quoting.value = false }
}
watch(() => [form.value.date_from, form.value.date_to, form.value.start_time, form.value.end_time], () => {
  clearTimeout(quoteTimer); quoteTimer = setTimeout(refreshQuote, 400)
}, { immediate: true })

function useSuggested() { form.value.price = quote.value.suggested_price }

function goPay() {
  err.value = ''
  if (!formValid()) { err.value = 'Lengkapi nama, tanggal, dan jam (selesai > mulai).'; return }
  if (selectedFac.value && selectedFac.value.size === 0) { err.value = 'Pilih minimal 1 lapangan.'; return }
  if (Number(form.value.price) < 0) { err.value = 'Harga tidak valid.'; return }
  phase.value = 'pay'
}

const result = ref(null)          // { event, order, conflicts }
async function onPay(payload) {
  err.value = ''
  try {
    const data = await pos.createEvent({ ...form.value, price: Number(form.value.price) || 0, facility_ids: facIdsParam() }, payload)
    result.value = data
    phase.value = 'result'
    emit('done')                  // beri tahu induk (mis. refresh jadwal)
  } catch (e) {
    err.value = e?.response?.data?.message || 'Gagal membuat event.'
    phase.value = 'form'
  }
}

// --- reschedule booking bentrok ---
const rescheduleOrder = ref(null)
async function openReschedule(c) {
  try { rescheduleOrder.value = await pos.getOrder(c.order_id) }
  catch { err.value = 'Gagal memuat order.' }
}
async function onRescheduled() {
  rescheduleOrder.value = null
  // refresh daftar konflik
  if (result.value?.event?.id) {
    try { const d = await pos.eventDetail(result.value.event.id); result.value.conflicts = d.conflicts } catch { /* */ }
  }
  emit('done')
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">🏆 Buat Event</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <!-- ===== FORM ===== -->
      <div v-if="phase === 'form'" class="space-y-3">
        <div class="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-800">
          Event mengunci <b>{{ allSelected ? 'semua lapangan' : 'lapangan terpilih' }}</b> di jam ini. Booking member yang bentrok bisa dipindah setelah event dibuat.
        </div>
        <div>
          <label class="text-xs text-slate-500">Nama event</label>
          <input v-model="form.name" placeholder="mis. Turnamen Futsal RT 05" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div><label class="text-xs text-slate-500">Penyewa</label>
            <input v-model="form.renter" placeholder="Nama/PIC" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none" /></div>
          <div><label class="text-xs text-slate-500">No. HP</label>
            <input v-model="form.phone" placeholder="08…" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none" /></div>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div><label class="text-xs text-slate-500">Tanggal mulai</label>
            <input v-model="form.date_from" type="date" :min="today" class="w-full rounded-lg border border-slate-300 px-2 py-2 text-sm outline-none" /></div>
          <div><label class="text-xs text-slate-500">Tanggal selesai</label>
            <input v-model="form.date_to" type="date" :min="form.date_from" class="w-full rounded-lg border border-slate-300 px-2 py-2 text-sm outline-none" /></div>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div><label class="text-xs text-slate-500">Jam mulai</label>
            <input v-model="form.start_time" type="time" class="w-full rounded-lg border border-slate-300 px-2 py-2 text-sm outline-none" /></div>
          <div><label class="text-xs text-slate-500">Jam selesai</label>
            <input v-model="form.end_time" type="time" class="w-full rounded-lg border border-slate-300 px-2 py-2 text-sm outline-none" /></div>
        </div>

        <!-- Pilih lapangan yang dipakai event -->
        <div v-if="facilities.length" class="border border-slate-200 rounded-lg p-3">
          <div class="flex items-center justify-between mb-2">
            <label class="text-xs font-medium text-slate-600">Lapangan dipakai event <span class="text-slate-400">({{ selectedFac ? selectedFac.size : 0 }}/{{ facilities.length }})</span></label>
            <button type="button" @click="selectAllFac" :class="allSelected ? 'text-slate-300' : 'text-brand-600'" class="text-xs" :disabled="allSelected">Pilih semua</button>
          </div>
          <div class="grid grid-cols-2 gap-1.5 max-h-40 overflow-auto">
            <label v-for="f in facilities" :key="f.id" class="flex items-center gap-2 text-sm rounded-lg px-2 py-1.5 cursor-pointer"
              :class="facSelected(f.id) ? 'bg-brand-50 text-brand-800' : 'bg-slate-50 text-slate-500'">
              <input type="checkbox" :checked="facSelected(f.id)" @change="toggleFac(f.id)" class="accent-brand-600" />
              <span class="truncate">{{ f.name }}</span>
            </label>
          </div>
          <p class="text-[11px] text-slate-400 mt-1.5">Hanya lapangan tercentang yang dikunci event; sisanya tetap bisa dibooking.</p>
        </div>

        <!-- Booking yang akan tertimpa event (dipindah jadwal setelah event dibuat) -->
        <div v-if="quote.conflict_count" class="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs">
          <p class="font-medium text-amber-800 mb-2">⚠️ {{ quote.conflict_count }} booking tertimpa event — akan dipindah jadwal setelah event dibuat:</p>
          <div class="max-h-40 overflow-auto space-y-1">
            <div v-for="c in quote.conflicts" :key="c.booking_id" class="bg-white rounded px-2 py-1 border border-amber-100">
              <div class="flex justify-between gap-2">
                <span class="text-slate-700 font-medium">{{ c.customer_name || 'Tanpa nama' }}<span v-if="c.is_member" class="ml-1 text-[10px] bg-purple-100 text-purple-700 rounded px-1">member</span></span>
                <span class="text-slate-500 whitespace-nowrap">{{ c.start_time }}–{{ c.end_time }}</span>
              </div>
              <div class="text-slate-400">{{ c.facility_name }} · {{ c.booking_date }}<span v-if="c.customer_phone"> · {{ c.customer_phone }}</span></div>
            </div>
          </div>
        </div>

        <div class="bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm">
          <div class="flex justify-between text-xs text-slate-500 mb-1">
            <span>{{ quote.facility_count }} lapangan • harga normal</span>
            <span v-if="quote.conflict_count" class="text-amber-600 font-medium">⚠️ {{ quote.conflict_count }} bentrok</span>
          </div>
          <label class="text-xs text-slate-500">Harga sewa event (bisa nego)</label>
          <div class="flex gap-2 items-center">
            <input v-model.number="form.price" type="number" inputmode="numeric" class="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-lg text-right outline-none focus:border-brand-500" />
            <button @click="useSuggested" type="button" class="text-xs text-brand-600 whitespace-nowrap">pakai usulan<br />{{ rupiah(quote.suggested_price) }}</button>
          </div>
        </div>

        <p v-if="err" class="text-sm text-red-600">{{ err }}</p>
        <button @click="goPay" class="w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-semibold">Lanjut ke Pembayaran →</button>
      </div>

      <!-- ===== RESULT / KONFLIK ===== -->
      <div v-else-if="phase === 'result'" class="space-y-3">
        <div class="bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 text-sm text-emerald-800">
          ✅ Event <b>{{ result.event.name }}</b> dibuat. Jadwal jam {{ result.event.start_time }}–{{ result.event.end_time }} terkunci.
        </div>
        <div v-if="result.conflicts.length">
          <p class="text-sm font-medium text-slate-700 mb-1">⚠️ {{ result.conflicts.length }} booking perlu dipindah:</p>
          <div class="space-y-2">
            <div v-for="c in result.conflicts" :key="c.booking_id" class="border rounded-lg p-2 flex justify-between items-center">
              <div class="text-sm">
                <p class="font-medium text-slate-800">{{ c.customer_name || 'Tanpa nama' }} <span v-if="c.is_member" class="text-[10px] bg-purple-100 text-purple-700 rounded px-1">member</span></p>
                <p class="text-xs text-slate-500">{{ c.facility_name }} · {{ c.booking_date }} {{ c.start_time }}-{{ c.end_time }}</p>
              </div>
              <button @click="openReschedule(c)" class="py-1.5 px-3 rounded-lg bg-teal-50 hover:bg-teal-100 text-teal-700 text-sm font-medium whitespace-nowrap">📅 Pindahkan</button>
            </div>
          </div>
        </div>
        <p v-else class="text-sm text-slate-500 text-center py-2">Tidak ada booking yang bentrok 🎉</p>
        <button @click="emit('close')" class="w-full py-3 rounded-lg bg-slate-800 text-white font-semibold">Selesai</button>
      </div>
    </div>

    <!-- Pembayaran sewa event -->
    <PaymentDialog v-if="phase === 'pay'" :total="Number(form.price) || 0" title="Bayar Sewa Event"
      :qris-dynamic="pos.qrisDynamic"
      @close="phase = 'form'" @pay="onPay" />

    <!-- Reschedule booking bentrok -->
    <RescheduleDialog v-if="rescheduleOrder" :order="rescheduleOrder"
      @close="rescheduleOrder = null" @done="onRescheduled" />
  </div>
</template>
