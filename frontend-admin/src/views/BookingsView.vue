<script setup>
import { ref, onMounted, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { parseUTC } from '../utils/datetime'

const auth = useAuthStore()
const isManager = computed(() => auth.user?.role === 'manager_unit')

const venues = ref([])
const venueId = ref('')
const today = new Date().toISOString().slice(0, 10)
const in30 = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10)
const from = ref(today)
const to = ref(in30)
const onlyUnpaid = ref(false)
const bookings = ref([])
const loading = ref(false)
const detail = ref(null)
const detailLoading = ref(false)

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function waLink(phone) {
  if (!phone) return null
  let digits = phone.replace(/\D/g, '')
  if (!digits) return null
  if (digits.startsWith('0')) digits = '62' + digits.slice(1)
  else if (!digits.startsWith('62')) digits = '62' + digits
  return `https://wa.me/${digits}`
}
function venueCode(id) { const v = venues.value.find((x) => x.id === id); return v ? v.code : '—' }
function fmtDate(d) {
  return new Date(d + 'T00:00:00').toLocaleDateString('id-ID', { weekday: 'short', day: '2-digit', month: 'short' })
}
function statusLabel(s) {
  return { paid: 'Lunas', partial: 'DP', open: 'Belum bayar', void: 'Batal' }[s] || s || '—'
}
function statusClass(s) {
  return {
    paid: 'bg-emerald-100 text-emerald-700',
    partial: 'bg-amber-100 text-amber-700',
    open: 'bg-slate-100 text-slate-500',
    void: 'bg-red-100 text-red-600',
  }[s] || 'bg-slate-100 text-slate-500'
}

const shown = computed(() =>
  onlyUnpaid.value ? bookings.value.filter((b) => b.payment_status === 'partial' || b.payment_status === 'open') : bookings.value,
)

// ringkasan — booking batal (void) dikeluarkan dari semua total nilai/uang
const activeBookings = computed(() => shown.value.filter((b) => b.payment_status !== 'void'))
const totalCount = computed(() => activeBookings.value.length)
const totalNilai = computed(() => activeBookings.value.reduce((s, b) => s + (b.order_total || 0), 0))
const totalDp = computed(() =>
  activeBookings.value
    .filter((b) => b.payment_status === 'partial')
    .reduce((s, b) => s + (b.order_paid || 0), 0),
)
const totalDue = computed(() => activeBookings.value.reduce((s, b) => s + (b.order_due || 0), 0))

const perVenue = computed(() => {
  const map = {}
  for (const b of activeBookings.value) {
    const vid = b.venue_id
    if (!map[vid]) map[vid] = { venue_id: vid, count: 0, total: 0, due: 0 }
    map[vid].count += 1
    map[vid].total += b.order_total || 0
    map[vid].due += b.order_due || 0
  }
  return Object.values(map).sort((a, b) => b.total - a.total)
})
function venueName(id) {
  const v = venues.value.find((x) => x.id === id)
  return v ? `${v.code} — ${v.name}` : `#${id}`
}

async function loadVenues() {
  const { data } = await client.get('/admin/venues')
  venues.value = data.venues
  if (isManager.value) {
    venues.value = venues.value.filter((x) => x.id === auth.user?.venue_id)
    venueId.value = auth.user?.venue_id || ''
  }
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
async function openDetail(b) {
  if (!b.order_id) return
  detailLoading.value = true
  detail.value = { loading: true }
  try {
    const { data } = await client.get(`/admin/orders/${b.order_id}`)
    detail.value = data.order
  } finally { detailLoading.value = false }
}
async function deleteEmpty(b) {
  if (!window.confirm(`Hapus baris booking kosong ${b.start_time}-${b.end_time} (${b.facility_name})?`)) return
  try {
    await client.delete(`/admin/bookings/${b.id}`)
    await run()
  } catch (e) {
    alert(e?.response?.data?.message || 'Gagal menghapus.')
  }
}
async function cancelBooking() {
  if (!detail.value?.id) return
  if (!window.confirm('Batalkan booking ini (no-show)?\nDP yang sudah dibayar HANGUS (tidak dikembalikan) dan slot dilepas.')) return
  try {
    await client.post(`/admin/orders/${detail.value.id}/cancel`)
    detail.value = null
    await run()
  } catch (e) {
    alert(e?.response?.data?.message || 'Gagal membatalkan.')
  }
}
onMounted(async () => { await loadVenues(); await run() })
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-800 mb-1">Booking Lapangan</h1>
    <p class="text-slate-500 mb-5">Jadwal booking + status pembayaran (DP / lunas). Klik baris untuk riwayat.</p>

    <div class="bg-white rounded-xl shadow-sm border p-4 mb-5 flex flex-wrap items-end gap-3">
      <div><label class="block text-xs text-slate-500 mb-1">Dari</label>
        <input v-model="from" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <div><label class="block text-xs text-slate-500 mb-1">Sampai</label>
        <input v-model="to" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      <div v-if="!isManager"><label class="block text-xs text-slate-500 mb-1">Venue</label>
        <select v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua venue</option>
          <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
        </select></div>
      <button @click="run" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-5 py-2 font-medium">Terapkan</button>
      <label class="flex items-center gap-2 text-sm text-slate-600 ml-2"><input v-model="onlyUnpaid" type="checkbox" /> Hanya belum lunas</label>
    </div>

    <!-- Ringkasan -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
      <div class="bg-white rounded-xl shadow-sm border p-4">
        <p class="text-xs text-slate-400 mb-1">Total Booking</p>
        <p class="text-xl font-bold text-slate-800">{{ totalCount }}</p>
      </div>
      <div class="bg-white rounded-xl shadow-sm border p-4">
        <p class="text-xs text-slate-400 mb-1">Total Nilai</p>
        <p class="text-xl font-bold text-slate-800">{{ rupiah(totalNilai) }}</p>
      </div>
      <div class="bg-white rounded-xl shadow-sm border p-4">
        <p class="text-xs text-slate-400 mb-1">Total DP Diterima</p>
        <p class="text-xl font-bold text-amber-600">{{ rupiah(totalDp) }}</p>
      </div>
      <div class="bg-white rounded-xl shadow-sm border p-4">
        <p class="text-xs text-slate-400 mb-1">Belum Lunas (Piutang)</p>
        <p class="text-xl font-bold text-red-600">{{ rupiah(totalDue) }}</p>
      </div>
    </div>

    <!-- Per venue -->
    <div v-if="perVenue.length > 1" class="bg-white rounded-xl shadow-sm border overflow-hidden mb-5">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-2.5 font-medium">Venue</th>
            <th class="px-4 py-2.5 font-medium text-right">Jml Booking</th>
            <th class="px-4 py-2.5 font-medium text-right">Total Nilai</th>
            <th class="px-4 py-2.5 font-medium text-right">Piutang</th>
          </tr></thead>
          <tbody>
            <tr v-for="pv in perVenue" :key="pv.venue_id" class="border-t">
              <td class="px-4 py-2.5 text-slate-700">{{ venueName(pv.venue_id) }}</td>
              <td class="px-4 py-2.5 text-right">{{ pv.count }}</td>
              <td class="px-4 py-2.5 text-right">{{ rupiah(pv.total) }}</td>
              <td class="px-4 py-2.5 text-right" :class="pv.due > 0 ? 'text-amber-600 font-medium' : 'text-slate-400'">{{ rupiah(pv.due) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th class="px-4 py-3 font-medium">Tanggal</th>
              <th class="px-4 py-3 font-medium">Jam</th>
              <th class="px-4 py-3 font-medium">Lapangan</th>
              <th class="px-4 py-3 font-medium">Customer</th>
              <th class="px-4 py-3 font-medium">No. HP</th>
              <th class="px-4 py-3 font-medium text-right">Total</th>
              <th class="px-4 py-3 font-medium text-right">Sisa</th>
              <th class="px-4 py-3 font-medium text-center">Status</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading"><td colspan="9" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!shown.length"><td colspan="9" class="px-4 py-8 text-center text-slate-400">Belum ada booking.</td></tr>
            <tr v-for="b in shown" :key="b.id" @click="openDetail(b)" class="border-t hover:bg-slate-50 cursor-pointer">
              <td class="px-4 py-3 text-slate-700">{{ fmtDate(b.booking_date) }}</td>
              <td class="px-4 py-3 font-medium text-slate-700">{{ b.start_time }}–{{ b.end_time }}</td>
              <td class="px-4 py-3 text-slate-700">{{ b.facility_name }}</td>
              <td class="px-4 py-3 text-slate-600">{{ b.customer_name || '—' }}</td>
              <td class="px-4 py-3">
                <a v-if="waLink(b.customer_phone)" :href="waLink(b.customer_phone)" target="_blank" rel="noopener"
                  @click.stop class="text-emerald-600 hover:underline whitespace-nowrap">
                  💬 {{ b.customer_phone }}
                </a>
                <span v-else class="text-slate-400">—</span>
              </td>
              <td class="px-4 py-3 text-right">{{ b.order_total != null ? rupiah(b.order_total) : '—' }}</td>
              <td class="px-4 py-3 text-right" :class="b.order_due > 0 ? 'text-amber-600 font-medium' : 'text-slate-400'">
                {{ b.order_due != null ? rupiah(b.order_due) : '—' }}
              </td>
              <td class="px-4 py-3 text-center">
                <span :class="statusClass(b.payment_status)" class="text-xs rounded-full px-2 py-0.5">{{ statusLabel(b.payment_status) }}</span>
              </td>
              <td class="px-4 py-3 text-right">
                <button v-if="!b.order_id" @click.stop="deleteEmpty(b)" class="text-red-500 text-xs hover:text-red-700">Hapus</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Detail / riwayat pembayaran -->
    <div v-if="detail" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="detail = null">
      <div class="bg-white w-full max-w-md rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-slate-800">Detail Order</h3>
          <button @click="detail = null" class="text-slate-400 text-xl">✕</button>
        </div>
        <p v-if="detailLoading" class="text-slate-400">Memuat…</p>
        <template v-else>
          <div class="flex justify-between text-sm mb-1">
            <span class="font-mono text-slate-500">{{ detail.order_number }}</span>
            <span :class="statusClass(detail.status)" class="text-xs rounded-full px-2 py-0.5">{{ statusLabel(detail.status) }}</span>
          </div>
          <p class="text-sm text-slate-600 mb-3">{{ detail.customer_name || 'Tanpa nama' }}<span v-if="detail.customer_phone"> · {{ detail.customer_phone }}</span></p>

          <p class="text-xs font-medium text-slate-400 mb-1">Item</p>
          <div v-for="it in detail.items" :key="it.id" class="flex justify-between text-sm mb-1">
            <span class="text-slate-600">{{ it.name }}</span><span>{{ rupiah(it.line_total) }}</span>
          </div>
          <div class="border-t my-2"></div>
          <div class="flex justify-between text-sm"><span class="text-slate-500">Total</span><span class="font-medium">{{ rupiah(detail.total_amount) }}</span></div>
          <div class="flex justify-between text-sm"><span class="text-slate-500">Terbayar</span><span class="text-emerald-600">{{ rupiah(detail.amount_paid) }}</span></div>
          <div v-if="detail.amount_due > 0" class="flex justify-between text-sm"><span class="text-slate-500">Sisa</span><span class="text-amber-600 font-medium">{{ rupiah(detail.amount_due) }}</span></div>

          <p class="text-xs font-medium text-slate-400 mt-4 mb-1">Riwayat pembayaran</p>
          <div v-if="!detail.payments.length" class="text-sm text-slate-400">Belum ada pembayaran.</div>
          <div v-for="p in detail.payments" :key="p.id" class="flex justify-between text-sm border-t py-1.5">
            <span class="text-slate-600">
              {{ p.method.toUpperCase() }}
              <span :class="p.status === 'paid' ? 'text-emerald-600' : 'text-amber-600'" class="text-xs">({{ p.status === 'paid' ? 'lunas' : p.status }})</span>
              <span v-if="p.paid_at" class="text-xs text-slate-400"> · {{ parseUTC(p.paid_at).toLocaleString('id-ID') }}</span>
            </span>
            <span class="font-medium">{{ rupiah(p.amount) }}</span>
          </div>

          <button v-if="detail.status === 'open' || detail.status === 'partial'" @click="cancelBooking"
            class="mt-5 w-full py-2.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-medium">
            Batalkan Booking (No-show) — DP hangus
          </button>
        </template>
      </div>
    </div>
  </div>
</template>
