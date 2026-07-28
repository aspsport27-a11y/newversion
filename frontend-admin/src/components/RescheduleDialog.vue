<script setup>
import { ref, computed, onMounted } from 'vue'
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
  } catch (e) {
    err.value = 'Gagal memuat lapangan.'
  }
})

const facility = computed(() => facilities.value.find((f) => f.id === facilityId.value))
const selectedItem = computed(() => bookingItems.value.find((i) => i.id === itemId.value))

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
  busy.value = true
  try {
    const { data } = await client.post(`/admin/orders/${props.order.id}/reschedule`, {
      order_item_id: itemId.value, facility_id: facilityId.value,
      booking_date: date.value, start_time: hhmm(startH.value), end_time: hhmm(endH.value),
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
