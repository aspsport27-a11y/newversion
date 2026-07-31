<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { parseUTC } from '../utils/datetime'
import WaIcon from '../components/WaIcon.vue'
import RescheduleDialog from '../components/RescheduleDialog.vue'

const auth = useAuthStore()
const isManager = computed(() => auth.user?.role === 'manager_unit')
const canReschedule = computed(() => auth.hasPerm('order.cancel'))
const rescheduleOrder = ref(null)
const detailVenueId = ref(null)

const venues = ref([])
const venueId = ref('')
const today = new Date().toISOString().slice(0, 10)
const in30 = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10)
const from = ref(today)
const to = ref(in30)
const onlyUnpaid = ref(false)
const showVoid = ref(false) // sembunyikan booking Batal secara default
// filter coach: '' = semua, 'any' = semua yg pakai coach, atau id coach tertentu
const coachFilter = ref('')
const coachList = ref([])
const bookings = ref([])
const loading = ref(false)
const detail = ref(null)
const detailLoading = ref(false)

const tab = ref('list') // 'list' | 'forfeited'
// DP Hangus (order batal yg DP-nya sudah masuk & tak direfund)
const fdRows = ref([])
const fdPerVenue = ref([])
const fdTotal = ref(0)
const fdLoading = ref(false)

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
  return new Date(d + 'T00:00:00').toLocaleDateString('id-ID', { weekday: 'long', day: '2-digit', month: 'short', year: 'numeric' })
}
// tanggal+jam pembayaran (datetime UTC dr backend) → waktu lokal singkat
function fmtPay(iso) {
  if (!iso) return '—'
  return parseUTC(iso).toLocaleString('id-ID', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
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

// Coaching cuma relevan di venue padel. Kalau venue tertentu dipilih → ikut
// tipe venue itu; kalau "Semua venue" → tampil selama ada venue padel dalam
// cakupan user. Pakai TIPE venue (bukan nama/id) spt pola waterpark.
const isPadelVenue = (v) => /padel/i.test(v?.type || '')
const showCoaching = computed(() => {
  if (venueId.value) return isPadelVenue(venues.value.find((v) => v.id === venueId.value))
  return venues.value.some(isPadelVenue)
})

const shown = computed(() => {
  let list = bookings.value
  if (!showVoid.value) list = list.filter((b) => b.payment_status !== 'void')
  if (onlyUnpaid.value) list = list.filter((b) => b.payment_status === 'partial' || b.payment_status === 'open')
  return list
})
// booking yg boleh dihapus permanen: kosong (tanpa order) ATAU batal TANPA
// uang (order_paid 0). Batal yg ada DP hangus TIDAK boleh (tersimpan utk laporan).
function canDelete(b) {
  if (!b.order_id) return true
  return b.payment_status === 'void' && !(b.order_paid > 0)
}

// ringkasan — booking batal (void) dikeluarkan dari semua total nilai/uang
const activeBookings = computed(() => shown.value.filter((b) => b.payment_status !== 'void'))
// 1 order (member) bisa punya banyak tanggal → uang JANGAN dihitung berkali-kali.
// Ambil 1 wakil per order utk hitungan uang; booking tanpa order dianggap unik.
const activeOrders = computed(() => {
  const seen = new Set(); const out = []
  for (const b of activeBookings.value) {
    const key = b.order_id ? 'o' + b.order_id : 'b' + b.id
    if (seen.has(key)) continue
    seen.add(key); out.push(b)
  }
  return out
})
const totalCount = computed(() => activeBookings.value.length) // jumlah sesi/jadwal
const totalNilai = computed(() => activeOrders.value.reduce((s, b) => s + (b.order_total || 0), 0))
const totalDp = computed(() =>
  activeOrders.value
    .filter((b) => b.payment_status === 'partial')
    .reduce((s, b) => s + (b.order_paid || 0), 0),
)
const totalDue = computed(() => activeOrders.value.reduce((s, b) => s + (b.order_due || 0), 0))

const perVenue = computed(() => {
  const map = {}
  const seenOrder = new Set()
  for (const b of activeBookings.value) {
    const vid = b.venue_id
    if (!map[vid]) map[vid] = { venue_id: vid, count: 0, total: 0, due: 0 }
    map[vid].count += 1 // sesi
    const okey = b.order_id ? 'o' + b.order_id : 'b' + b.id
    if (!seenOrder.has(okey)) {
      seenOrder.add(okey)
      map[vid].total += b.order_total || 0
      map[vid].due += b.order_due || 0
    }
  }
  return Object.values(map).sort((a, b) => b.total - a.total)
})

// kelompokkan baris per order: order dgn >1 tanggal (member) → accordion
// (1 baris ringkas + rincian tanggal saat dibuka); order 1 tanggal → baris biasa
const openOrders = ref(new Set())
function toggleOrder(id) {
  const s = new Set(openOrders.value)
  s.has(id) ? s.delete(id) : s.add(id)
  openOrders.value = s
}
const grouped = computed(() => {
  const orderMap = new Map(); const items = []
  for (const b of shown.value) {
    if (!b.order_id) { items.push({ key: 'b' + b.id, type: 'single', b }); continue }
    if (!orderMap.has(b.order_id)) {
      const grp = { key: 'o' + b.order_id, type: 'group', order_id: b.order_id, parent: b, children: [] }
      orderMap.set(b.order_id, grp); items.push(grp)
    }
    orderMap.get(b.order_id).children.push(b)
  }
  return items.map((it) =>
    it.type === 'group' && it.children.length === 1 ? { key: it.key, type: 'single', b: it.children[0] } : it,
  )
})
function grpDateRange(children) {
  const ds = children.map((c) => c.booking_date).sort()
  const f = (d) => new Date(d + 'T00:00:00').toLocaleDateString('id-ID', { day: '2-digit', month: 'short' })
  return ds.length > 1 ? `${f(ds[0])} – ${f(ds[ds.length - 1])}` : f(ds[0])
}
function grpJam(children) {
  const set = new Set(children.map((c) => `${c.start_time}–${c.end_time}`))
  return set.size === 1 ? [...set][0] : 'beragam'
}
function venueName(id) {
  const v = venues.value.find((x) => x.id === id)
  return v ? `${v.code} — ${v.name}` : `#${id}`
}

// cetak daftar booking sesuai filter aktif (tanggal/venue/status) — buka
// window baru berisi tabel rapi lalu panggil print (tak ganggu layout portal)
function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
}
function printBookings() {
  const rangeLabel = `${fmtDate(from.value)} — ${fmtDate(to.value)}`
  const venueLabel = venueId.value ? venueName(venueId.value) : 'Semua venue'
  const printedAt = new Date().toLocaleString('id-ID')
  const body = shown.value.map((b) => `<tr>
    <td>${esc(fmtDate(b.booking_date))}</td>
    <td>${esc(b.start_time)}–${esc(b.end_time)}</td>
    <td>${esc(b.facility_name || '—')}</td>
    <td>${b.coach_name ? esc(b.coach_name) + (b.coaching_persons ? ` (${b.coaching_persons} org)` : '') : '—'}</td>
    <td>${esc(b.customer_name || '—')}</td>
    <td>${esc(b.customer_phone || '—')}</td>
    <td class="r">${b.order_total != null ? esc(rupiah(b.order_total)) : '—'}</td>
    <td class="r">${b.order_due != null ? esc(rupiah(b.order_due)) : '—'}</td>
    <td>${esc(fmtPay(b.dp_at))}</td>
    <td>${esc(fmtPay(b.paid_off_at))}</td>
    <td>${esc(statusLabel(b.payment_status))}</td>
  </tr>`).join('')
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>Laporan Booking</title>
  <style>
    body{font-family:Arial,Helvetica,sans-serif;color:#1e293b;margin:24px;font-size:12px}
    h1{font-size:18px;margin:0 0 4px}
    .meta{color:#64748b;font-size:12px;margin-bottom:12px}
    table{width:100%;border-collapse:collapse}
    th,td{border:1px solid #cbd5e1;padding:5px 7px;text-align:left}
    th{background:#f1f5f9}
    .r{text-align:right;white-space:nowrap}
    tfoot td{font-weight:bold;background:#f8fafc}
    @media print{body{margin:10mm}}
  </style></head><body>
    <h1>Laporan Booking Lapangan</h1>
    <div class="meta">Periode main: ${esc(rangeLabel)} · Venue: ${esc(venueLabel)} · Dicetak: ${esc(printedAt)}<br>
      Jumlah: ${totalCount.value} booking · Total nilai: ${esc(rupiah(totalNilai.value))} · DP diterima: ${esc(rupiah(totalDp.value))} · Piutang: ${esc(rupiah(totalDue.value))}</div>
    <table>
      <thead><tr>
        <th>Tanggal Main</th><th>Jam</th><th>Lapangan</th><th>Coach</th><th>Customer</th><th>No. HP</th>
        <th class="r">Total</th><th class="r">Sisa</th><th>Tgl DP</th><th>Tgl Lunas</th><th>Status</th>
      </tr></thead>
      <tbody>${body || '<tr><td colspan="11" style="text-align:center;color:#94a3b8">Tidak ada data.</td></tr>'}</tbody>
    </table>
  </body></html>`
  const w = window.open('', '_blank')
  if (!w) { alert('Popup diblokir browser — izinkan popup untuk mencetak.'); return }
  w.document.write(html)
  w.document.close()
  w.focus()
  setTimeout(() => w.print(), 300)
}

async function loadVenues() {
  const { data } = await client.get('/admin/venues')
  venues.value = data.venues
  if (isManager.value) {
    venues.value = venues.value.filter((x) => x.id === auth.user?.venue_id)
    venueId.value = auth.user?.venue_id || ''
  }
}
function params() {
  const p = { from: from.value, to: to.value }
  if (venueId.value) p.venue_id = venueId.value
  if (coachFilter.value) p.coach_id = coachFilter.value
  return p
}
// daftar coach utk dropdown filter — kosong kalau venue tak punya coaching,
// dan filternya otomatis disembunyikan
async function loadCoachList() {
  if (!showCoaching.value) { coachList.value = []; coachFilter.value = ''; return }
  try {
    const { data } = await client.get('/admin/coaches', {
      params: venueId.value ? { venue_id: venueId.value } : {},
    })
    coachList.value = (data.coaches || []).filter((c) => c.is_active)
  } catch (_) { coachList.value = [] }
  if (coachFilter.value && coachFilter.value !== 'any' &&
      !coachList.value.some((c) => String(c.id) === String(coachFilter.value))) {
    coachFilter.value = '' // coach terpilih tak ada di venue ini lagi
  }
}
async function run() {
  loading.value = true
  try {
    await loadCoachList()
    const { data } = await client.get('/admin/bookings', { params: params() })
    bookings.value = data.bookings
  } finally { loading.value = false }
  if (tab.value === 'forfeited') loadForfeited()
  if (tab.value === 'coaching') loadCoachingReport()
}
async function loadForfeited() {
  fdLoading.value = true
  try {
    const { data } = await client.get('/admin/bookings/forfeited-dp', { params: params() })
    fdRows.value = data.rows
    fdPerVenue.value = data.per_venue
    fdTotal.value = data.total
  } finally { fdLoading.value = false }
}
// ---------- Data Customer (CRM booking) ----------
const custRows = ref([])
const custLoading = ref(false)
const custSearch = ref('')
const custFilter = ref('') // '' | 'member' | 'reguler'
const custSort = ref('last') // last | count | spend | idle
const custDetail = ref(null) // { customer, history }
async function loadCustomers() {
  custLoading.value = true
  try {
    const { data } = await client.get('/admin/customers')
    custRows.value = data.customers
  } finally { custLoading.value = false }
}
const custShown = computed(() => {
  let list = custRows.value
  if (custFilter.value === 'member') list = list.filter((c) => c.is_member)
  else if (custFilter.value === 'reguler') list = list.filter((c) => !c.is_member)
  const q = custSearch.value.trim().toLowerCase()
  if (q) list = list.filter((c) => (c.name || '').toLowerCase().includes(q) || (c.phone || '').includes(q))
  const arr = [...list]
  if (custSort.value === 'count') arr.sort((a, b) => b.booking_count - a.booking_count)
  else if (custSort.value === 'spend') arr.sort((a, b) => b.total_spend - a.total_spend)
  else if (custSort.value === 'hours') arr.sort((a, b) => (b.total_hours || 0) - (a.total_hours || 0))
  else if (custSort.value === 'idle') arr.sort((a, b) => (a.last_visit || '').localeCompare(b.last_visit || '')) // lama tak datang dulu
  else arr.sort((a, b) => (b.last_visit || '').localeCompare(a.last_visit || ''))
  return arr
})
function fmtVisit(iso) { return iso ? parseUTC(iso).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) : '—' }
function fmtHours(n) { const h = Number(n) || 0; return `${Number.isInteger(h) ? h : h.toFixed(1)} jam` }
async function openCustomer(c) {
  custDetail.value = { customer: c, history: null }
  try {
    const { data } = await client.get('/admin/customers/history', { params: { key: c.key } })
    custDetail.value = { customer: c, history: data.history }
  } catch { custDetail.value = { customer: c, history: [] } }
}
function exportCustomersCsv() {
  const head = ['Nama', 'No HP', 'Jumlah Booking', 'Total Jam Main', 'Total Belanja', 'Terakhir Booking', 'Venue Favorit', 'Status']
  const rows = custShown.value.map((c) => [
    c.name, c.phone || '', c.booking_count, c.total_hours || 0, c.total_spend,
    c.last_visit ? c.last_visit.slice(0, 10) : '', c.favorite_venue || '',
    c.is_member ? 'Member' : 'Reguler',
  ])
  const csv = [head, ...rows].map((r) => r.map((x) => `"${String(x).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `data-customer-${today}.csv`
  a.click()
}

// ---------- Rekap Coaching (per coach) ----------
const chRows = ref([])
const chCoaches = ref([])
const chTotal = ref({ sessions: 0, hours: 0, revenue: 0 })
const chLoading = ref(false)
const chDetailCoach = ref(null) // coach_id yg rincian sesinya sedang dibuka
async function loadCoachingReport() {
  chLoading.value = true
  try {
    const { data } = await client.get('/admin/reports/coaching', { params: params() })
    chRows.value = data.rows
    chCoaches.value = data.coaches
    chTotal.value = data.total
  } catch (_) {
    chRows.value = []; chCoaches.value = []; chTotal.value = { sessions: 0, hours: 0, revenue: 0 }
  } finally { chLoading.value = false }
}
const chDetailRows = computed(() =>
  chDetailCoach.value == null ? [] : chRows.value.filter((r) => r.coach_id === chDetailCoach.value),
)
const chDetailName = computed(() =>
  chCoaches.value.find((c) => c.coach_id === chDetailCoach.value)?.coach_name || '',
)
function fmtJam(n) { const h = Number(n) || 0; return `${Number.isInteger(h) ? h : h.toFixed(1)} jam` }
function exportCoachingCsv() {
  const head = ['Tanggal Main', 'Jam', 'Venue', 'Lapangan', 'Coach', 'Peserta', 'Durasi (jam)', 'Nilai Coaching', 'Customer', 'No. Order']
  const rows = chRows.value.map((r) => [
    r.booking_date, `${r.start_time}-${r.end_time}`, r.venue_code, r.facility_name,
    r.coach_name, r.persons, r.hours, r.revenue, r.customer_name || '', r.order_number || '',
  ])
  const csv = [head, ...rows].map((a) => a.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' }))
  const a = document.createElement('a')
  a.href = url; a.download = `rekap-coaching_${from.value}_${to.value}.csv`; a.click()
  URL.revokeObjectURL(url)
}

function switchTab(t) {
  tab.value = t
  if (t === 'forfeited' && !fdRows.value.length) loadForfeited()
  if (t === 'customers' && !custRows.value.length) loadCustomers()
  if (t === 'coaching') loadCoachingReport()
}
function fmtDatesShort(arr) {
  return (arr || []).map((d) => {
    const dt = new Date(d + 'T00:00:00')
    return String(dt.getDate()).padStart(2, '0') + '/' + String(dt.getMonth() + 1).padStart(2, '0')
  }).join(', ')
}
async function openDetail(b) {
  if (!b.order_id) return
  detailVenueId.value = b.venue_id
  detailLoading.value = true
  detail.value = { loading: true }
  try {
    const { data } = await client.get(`/admin/orders/${b.order_id}`)
    detail.value = data.order
  } finally { detailLoading.value = false }
}
async function onRescheduled(res) {
  const info = res.reschedule || {}
  rescheduleOrder.value = null
  // muat ulang detail order supaya status/harga terbaru tampil
  if (detail.value?.id) {
    try {
      const { data } = await client.get(`/admin/orders/${detail.value.id}`)
      detail.value = data.order
    } catch { /* biarkan */ }
  }
  await run()
  const refunded = Number(info.refunded || 0)
  const due = Number(info.amount_due || 0)
  if (refunded > 0) alert(`Reschedule berhasil. Kelebihan ${rupiah(refunded)} dicatat sebagai kas keluar (refund).`)
  else if (due > 0) alert(`Reschedule berhasil. Sisa tagih ke customer ${rupiah(due)}.`)
  else alert('Reschedule berhasil.')
}
async function deleteBooking(b) {
  try {
    if (!b.order_id) {
      // booking kosong tanpa order → hapus baris booking-nya saja
      if (!window.confirm(`Hapus baris booking kosong ${b.start_time}-${b.end_time} (${b.facility_name})?`)) return
      await client.delete(`/admin/bookings/${b.id}`)
    } else {
      // order batal tanpa DP → hapus seluruh order (semua tanggalnya sekaligus)
      if (!window.confirm(`Hapus permanen transaksi batal ${b.order_number} (${b.customer_name || 'tanpa nama'})?`)) return
      await client.delete(`/admin/orders/${b.order_id}`)
    }
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
// pindah ke venue non-padel saat tab Rekap Coaching terbuka → kembali ke daftar
watch(showCoaching, (ada) => { if (!ada && tab.value === 'coaching') tab.value = 'list' })
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
      <div v-if="tab === 'list' && coachList.length">
        <label class="block text-xs text-slate-500 mb-1">Coach</label>
        <select v-model="coachFilter" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua booking</option>
          <option value="any">Hanya yang pakai coach</option>
          <option v-for="c in coachList" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
        </select>
      </div>
      <button @click="run" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-5 py-2 font-medium">Terapkan</button>
      <label v-if="tab === 'list'" class="flex items-center gap-2 text-sm text-slate-600 ml-2"><input v-model="onlyUnpaid" type="checkbox" /> Hanya belum lunas</label>
      <label v-if="tab === 'list'" class="flex items-center gap-2 text-sm text-slate-600"><input v-model="showVoid" type="checkbox" /> Tampilkan yang batal</label>
      <button v-if="tab === 'list'" @click="printBookings" class="ml-auto bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm rounded-lg px-4 py-2 font-medium">🖨️ Cetak</button>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 mb-5 border-b">
      <button @click="switchTab('list')" :class="tab === 'list' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Booking</button>
      <button @click="switchTab('forfeited')" :class="tab === 'forfeited' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">DP Hangus</button>
      <button @click="switchTab('customers')" :class="tab === 'customers' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Data Customer</button>
      <button v-if="showCoaching" @click="switchTab('coaching')" :class="tab === 'coaching' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Rekap Coaching</button>
    </div>

    <!-- ================= TAB DATA CUSTOMER (CRM) ================= -->
    <div v-if="tab === 'customers'">
      <div class="flex flex-wrap items-center gap-2 mb-4">
        <input v-model="custSearch" placeholder="🔍 Cari nama / no HP…" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500 w-56" />
        <select v-model="custFilter" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="">Semua</option>
          <option value="member">Member</option>
          <option value="reguler">Reguler</option>
        </select>
        <select v-model="custSort" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
          <option value="last">Terbaru booking</option>
          <option value="idle">Lama tak datang</option>
          <option value="count">Paling sering</option>
          <option value="hours">Jam main terbanyak</option>
          <option value="spend">Belanja terbesar</option>
        </select>
        <span class="text-xs text-slate-400">{{ custShown.length }} customer</span>
        <button @click="exportCustomersCsv" class="ml-auto bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm rounded-lg px-4 py-2 font-medium">📥 Export CSV</button>
      </div>

      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-4 py-3 font-medium">Nama</th>
              <th class="px-4 py-3 font-medium">No HP</th>
              <th class="px-4 py-3 font-medium text-center">Status</th>
              <th class="px-4 py-3 font-medium text-right">Booking</th>
              <th class="px-4 py-3 font-medium text-right">Total Jam Main</th>
              <th class="px-4 py-3 font-medium text-right">Total Belanja</th>
              <th class="px-4 py-3 font-medium">Terakhir</th>
              <th class="px-4 py-3 font-medium">Venue Fav.</th>
              <th class="px-4 py-3"></th>
            </tr></thead>
            <tbody>
              <tr v-if="custLoading"><td colspan="9" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
              <tr v-else-if="!custRows.length"><td colspan="9" class="px-4 py-8 text-center text-slate-400">Belum ada data customer booking.</td></tr>
              <tr v-else-if="!custShown.length"><td colspan="9" class="px-4 py-8 text-center text-slate-400">Tidak ada yang cocok.</td></tr>
              <tr v-for="c in custShown" :key="c.key" class="border-t hover:bg-slate-50 cursor-pointer" @click="openCustomer(c)">
                <td class="px-4 py-3 font-medium text-slate-700">{{ c.name }}</td>
                <td class="px-4 py-3 text-slate-500 font-mono text-xs">
                  {{ c.phone || '—' }}
                  <a v-if="waLink(c.phone)" :href="waLink(c.phone)" target="_blank" rel="noopener" @click.stop class="ml-1" title="Chat WhatsApp"><WaIcon /></a>
                </td>
                <td class="px-4 py-3 text-center">
                  <span v-if="c.is_member" class="text-[10px] bg-purple-100 text-purple-700 rounded-full px-2 py-0.5">Member</span>
                  <span v-else class="text-[10px] text-slate-400">Reguler</span>
                </td>
                <td class="px-4 py-3 text-right">{{ c.booking_count }}</td>
                <td class="px-4 py-3 text-right text-slate-600 whitespace-nowrap">{{ fmtHours(c.total_hours) }}</td>
                <td class="px-4 py-3 text-right font-medium">{{ rupiah(c.total_spend) }}</td>
                <td class="px-4 py-3 text-slate-500 whitespace-nowrap">{{ fmtVisit(c.last_visit) }}</td>
                <td class="px-4 py-3 text-slate-500">{{ c.favorite_venue || '—' }}</td>
                <td class="px-4 py-3 text-right text-brand-600 text-xs">Riwayat ›</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <p class="text-xs text-slate-400 mt-2">Data dari booking (non-batal), dikelompokkan per no HP. Klik baris untuk riwayat booking customer.</p>
    </div>

    <!-- Modal riwayat customer -->
    <div v-if="custDetail" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="custDetail = null">
      <div class="bg-white w-full max-w-lg rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-start mb-3">
          <div>
            <h3 class="text-lg font-bold text-slate-800">{{ custDetail.customer.name }}
              <span v-if="custDetail.customer.is_member" class="text-[10px] bg-purple-100 text-purple-700 rounded-full px-2 py-0.5 align-middle">Member</span>
            </h3>
            <p class="text-sm text-slate-500 font-mono">{{ custDetail.customer.phone || 'tanpa HP' }}
              <a v-if="waLink(custDetail.customer.phone)" :href="waLink(custDetail.customer.phone)" target="_blank" rel="noopener" class="ml-1 inline-flex items-center gap-1 text-emerald-600"><WaIcon /> WA</a>
            </p>
          </div>
          <button @click="custDetail = null" class="text-slate-400 hover:text-slate-600 text-xl leading-none">✕</button>
        </div>
        <div class="grid grid-cols-4 gap-2 mb-3 text-center">
          <div class="bg-slate-50 rounded-lg p-2"><p class="text-[11px] text-slate-500">Booking</p><p class="font-bold text-slate-700">{{ custDetail.customer.booking_count }}</p></div>
          <div class="bg-slate-50 rounded-lg p-2"><p class="text-[11px] text-slate-500">Jam Main</p><p class="font-bold text-slate-700 text-sm">{{ fmtHours(custDetail.customer.total_hours) }}</p></div>
          <div class="bg-slate-50 rounded-lg p-2"><p class="text-[11px] text-slate-500">Total Belanja</p><p class="font-bold text-slate-700 text-sm">{{ rupiah(custDetail.customer.total_spend) }}</p></div>
          <div class="bg-slate-50 rounded-lg p-2"><p class="text-[11px] text-slate-500">Terakhir</p><p class="font-bold text-slate-700 text-sm">{{ fmtVisit(custDetail.customer.last_visit) }}</p></div>
        </div>
        <p class="text-xs font-medium text-slate-500 mb-1">Riwayat Booking</p>
        <p v-if="!custDetail.history" class="text-sm text-slate-400 py-3">Memuat…</p>
        <p v-else-if="!custDetail.history.length" class="text-sm text-slate-400 py-3">Belum ada riwayat.</p>
        <div v-else class="space-y-1">
          <div v-for="h in custDetail.history" :key="h.order_id" class="border rounded-lg p-2 text-sm">
            <div class="flex justify-between">
              <span class="font-mono text-xs text-slate-500">{{ h.order_number }}</span>
              <span :class="statusClass(h.status)" class="text-[10px] rounded-full px-2 py-0.5">{{ statusLabel(h.status) }}</span>
            </div>
            <div class="text-slate-700">{{ (h.slots || []).join(', ') }}</div>
            <div class="flex justify-between text-xs text-slate-500">
              <span>{{ h.venue_code }} · {{ fmtVisit(h.created_at) }}</span>
              <span>{{ rupiah(h.total_amount) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ================= TAB REKAP COACHING ================= -->
    <div v-if="tab === 'coaching'">
      <div class="bg-teal-50 border border-teal-200 rounded-lg px-4 py-2.5 mb-4 text-sm text-teal-800">
        Dihitung berdasarkan <b>tanggal main</b> (kapan coach mengajar), bukan tanggal pembayaran —
        jadi angkanya bisa beda dengan laporan penjualan yang berbasis kas. Sesi yang dibatalkan tidak dihitung.
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
        <div class="bg-white rounded-xl shadow-sm border p-5">
          <p class="text-sm text-slate-500">Jumlah Sesi</p>
          <p class="text-2xl font-bold text-slate-800 mt-1">{{ chTotal.sessions }}</p>
        </div>
        <div class="bg-white rounded-xl shadow-sm border p-5">
          <p class="text-sm text-slate-500">Total Jam Mengajar</p>
          <p class="text-2xl font-bold text-slate-800 mt-1">{{ fmtJam(chTotal.hours) }}</p>
        </div>
        <div class="bg-white rounded-xl shadow-sm border p-5">
          <p class="text-sm text-slate-500">Nilai Coaching</p>
          <p class="text-2xl font-bold text-teal-700 mt-1">{{ rupiah(chTotal.revenue) }}</p>
        </div>
      </div>

      <div class="flex items-center justify-between mb-3">
        <p class="text-sm text-slate-500">Klik baris untuk melihat rincian sesi tiap coach.</p>
        <button v-if="chRows.length" @click="exportCoachingCsv" class="bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm rounded-lg px-4 py-2 font-medium">📥 Export CSV</button>
      </div>

      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-4 py-3 font-medium">Coach</th>
              <th class="px-4 py-3 font-medium text-right">Sesi</th>
              <th class="px-4 py-3 font-medium text-right">Jam Mengajar</th>
              <th class="px-4 py-3 font-medium text-right">Total Peserta</th>
              <th class="px-4 py-3 font-medium text-right">Nilai Coaching</th>
              <th class="px-4 py-3"></th>
            </tr></thead>
            <tbody>
              <tr v-if="chLoading"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
              <tr v-else-if="!chCoaches.length"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Belum ada sesi coaching pada periode ini.</td></tr>
              <tr v-for="c in chCoaches" :key="c.coach_id" class="border-t hover:bg-slate-50 cursor-pointer" @click="chDetailCoach = c.coach_id">
                <td class="px-4 py-3 font-medium text-slate-700">🎾 {{ c.coach_name }}</td>
                <td class="px-4 py-3 text-right">{{ c.sessions }}</td>
                <td class="px-4 py-3 text-right font-medium">{{ fmtJam(c.hours) }}</td>
                <td class="px-4 py-3 text-right text-slate-500">{{ c.persons_total }}</td>
                <td class="px-4 py-3 text-right font-medium text-teal-700">{{ rupiah(c.revenue) }}</td>
                <td class="px-4 py-3 text-right text-brand-600 text-xs">Rincian ›</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Modal rincian sesi per coach -->
    <div v-if="chDetailCoach != null" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" @click.self="chDetailCoach = null">
      <div class="bg-white w-full max-w-2xl rounded-2xl p-5 max-h-[90vh] overflow-auto">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-slate-800">🎾 {{ chDetailName }} — rincian sesi</h3>
          <button @click="chDetailCoach = null" class="text-slate-400 text-xl">✕</button>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-3 py-2 font-medium">Tanggal</th>
              <th class="px-3 py-2 font-medium">Jam</th>
              <th class="px-3 py-2 font-medium">Lapangan</th>
              <th class="px-3 py-2 font-medium">Customer</th>
              <th class="px-3 py-2 font-medium text-right">Peserta</th>
              <th class="px-3 py-2 font-medium text-right">Nilai</th>
            </tr></thead>
            <tbody>
              <tr v-for="r in chDetailRows" :key="r.booking_id" class="border-t">
                <td class="px-3 py-2 text-slate-600 whitespace-nowrap">{{ fmtDate(r.booking_date) }}</td>
                <td class="px-3 py-2 text-slate-700 whitespace-nowrap">{{ r.start_time }}–{{ r.end_time }}</td>
                <td class="px-3 py-2 text-slate-600">{{ r.venue_code }} · {{ r.facility_name }}</td>
                <td class="px-3 py-2 text-slate-600">{{ r.customer_name || '—' }}</td>
                <td class="px-3 py-2 text-right">{{ r.persons }}</td>
                <td class="px-3 py-2 text-right font-medium">{{ rupiah(r.revenue) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ================= TAB DP HANGUS ================= -->
    <div v-if="tab === 'forfeited'">
      <div class="bg-white rounded-xl shadow-sm border p-4 mb-5">
        <p class="text-xs text-slate-400 mb-1">Total DP hangus (periode ini)</p>
        <p class="text-2xl font-bold text-red-600">{{ rupiah(fdTotal) }}</p>
        <p class="text-xs text-slate-400 mt-1">Uang dari booking yang dibatalkan &amp; DP-nya tidak dikembalikan. Sudah tercatat di kas — daftar ini cuma untuk visibilitas per venue.</p>
      </div>

      <div v-if="fdPerVenue.length > 1" class="bg-white rounded-xl shadow-sm border overflow-hidden mb-5">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-2.5 font-medium">Venue</th>
            <th class="px-4 py-2.5 font-medium text-right">Jml</th>
            <th class="px-4 py-2.5 font-medium text-right">DP Hangus</th>
          </tr></thead>
          <tbody>
            <tr v-for="pv in fdPerVenue" :key="pv.venue_id" class="border-t">
              <td class="px-4 py-2.5 text-slate-700">{{ pv.venue_code }}</td>
              <td class="px-4 py-2.5 text-right">{{ pv.count }}</td>
              <td class="px-4 py-2.5 text-right text-red-600 font-medium">{{ rupiah(pv.total) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-4 py-3 font-medium">Tgl DP</th>
              <th class="px-4 py-3 font-medium">Venue</th>
              <th class="px-4 py-3 font-medium">Customer</th>
              <th class="px-4 py-3 font-medium">Tanggal main (batal)</th>
              <th class="px-4 py-3 font-medium text-right">DP Hangus</th>
            </tr></thead>
            <tbody>
              <tr v-if="fdLoading"><td colspan="5" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
              <tr v-else-if="!fdRows.length"><td colspan="5" class="px-4 py-8 text-center text-slate-400">Tidak ada DP hangus pada periode ini 🎉</td></tr>
              <tr v-for="r in fdRows" :key="r.order_id" class="border-t hover:bg-slate-50">
                <td class="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">{{ fmtPay(r.dp_at) }}</td>
                <td class="px-4 py-3 text-slate-700">{{ r.venue_code }}</td>
                <td class="px-4 py-3 text-slate-600">{{ r.customer_name || '—' }}</td>
                <td class="px-4 py-3 text-slate-500 text-xs">{{ fmtDatesShort(r.booking_dates) }}</td>
                <td class="px-4 py-3 text-right text-red-600 font-medium">{{ rupiah(r.forfeited) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ================= TAB BOOKING (list) ================= -->
    <template v-if="tab === 'list'">
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
              <th class="px-4 py-3 font-medium">Tanggal Main</th>
              <th class="px-4 py-3 font-medium">Jam</th>
              <th class="px-4 py-3 font-medium">Lapangan</th>
              <th v-if="showCoaching" class="px-4 py-3 font-medium">Coach</th>
              <th class="px-4 py-3 font-medium">Customer</th>
              <th class="px-4 py-3 font-medium">No. HP</th>
              <th class="px-4 py-3 font-medium text-right">Total</th>
              <th class="px-4 py-3 font-medium text-right">Sisa</th>
              <th class="px-4 py-3 font-medium">Tgl DP</th>
              <th class="px-4 py-3 font-medium">Tgl Lunas</th>
              <th class="px-4 py-3 font-medium text-center">Status</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading"><td :colspan="showCoaching ? 12 : 11" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!shown.length"><td :colspan="showCoaching ? 12 : 11" class="px-4 py-8 text-center text-slate-400">Belum ada booking.</td></tr>
            <template v-for="it in grouped" :key="it.key">
              <!-- baris tunggal (order 1 tanggal / booking tanpa order) -->
              <tr v-if="it.type === 'single'" @click="openDetail(it.b)" class="border-t hover:bg-slate-50 cursor-pointer">
                <td class="px-4 py-3 text-slate-700">{{ fmtDate(it.b.booking_date) }}</td>
                <td class="px-4 py-3 font-medium text-slate-700">{{ it.b.start_time }}–{{ it.b.end_time }}</td>
                <td class="px-4 py-3 text-slate-700">{{ it.b.facility_name }}</td>
                <td v-if="showCoaching" class="px-4 py-3 whitespace-nowrap">
                  <span v-if="it.b.coach_name" class="text-xs bg-teal-100 text-teal-700 rounded px-1.5 py-0.5">
                    🎾 {{ it.b.coach_name }}<span v-if="it.b.coaching_persons" class="text-teal-600"> · {{ it.b.coaching_persons }} org</span>
                  </span>
                  <span v-if="it.b.coaching_override" class="ml-1 text-xs bg-amber-100 text-amber-700 rounded px-1.5 py-0.5"
                    title="Dibuat di luar jam ketersediaan coach — kasir mengonfirmasi coach bersedia">⚠️ di luar jam</span>
                  <span v-else class="text-slate-300">—</span>
                </td>
                <td class="px-4 py-3 text-slate-600">{{ it.b.customer_name || '—' }}</td>
                <td class="px-4 py-3">
                  <a v-if="waLink(it.b.customer_phone)" :href="waLink(it.b.customer_phone)" target="_blank" rel="noopener" @click.stop class="text-emerald-600 hover:underline whitespace-nowrap inline-flex items-center gap-1"><WaIcon /> {{ it.b.customer_phone }}</a>
                  <span v-else class="text-slate-400">—</span>
                </td>
                <td class="px-4 py-3 text-right">{{ it.b.order_total != null ? rupiah(it.b.order_total) : '—' }}</td>
                <td class="px-4 py-3 text-right" :class="it.b.order_due > 0 ? 'text-amber-600 font-medium' : 'text-slate-400'">{{ it.b.order_due != null ? rupiah(it.b.order_due) : '—' }}</td>
                <td class="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">{{ fmtPay(it.b.dp_at) }}</td>
                <td class="px-4 py-3 whitespace-nowrap text-xs" :class="it.b.paid_off_at ? 'text-emerald-600' : 'text-slate-400'">{{ fmtPay(it.b.paid_off_at) }}</td>
                <td class="px-4 py-3 text-center"><span :class="statusClass(it.b.payment_status)" class="text-xs rounded-full px-2 py-0.5">{{ statusLabel(it.b.payment_status) }}</span></td>
                <td class="px-4 py-3 text-right"><button v-if="canDelete(it.b)" @click.stop="deleteBooking(it.b)" class="text-red-500 text-xs hover:text-red-700">Hapus</button></td>
              </tr>

              <!-- baris induk member (banyak tanggal) — accordion, uang tampil SEKALI -->
              <tr v-else @click="toggleOrder(it.order_id)" class="border-t bg-slate-50/50 hover:bg-slate-100 cursor-pointer">
                <td class="px-4 py-3 text-slate-700 whitespace-nowrap">
                  <span class="inline-block transition-transform mr-1 text-slate-400" :class="openOrders.has(it.order_id) ? 'rotate-90' : ''">▸</span>
                  <span class="font-medium">{{ it.children.length }} sesi</span>
                  <span class="text-xs text-slate-400 ml-1">{{ grpDateRange(it.children) }}</span>
                  <span class="ml-1 text-[10px] bg-purple-100 text-purple-700 rounded px-1.5 py-0.5">Member</span>
                </td>
                <td class="px-4 py-3 text-slate-500 text-sm">{{ grpJam(it.children) }}</td>
                <td class="px-4 py-3 text-slate-700">{{ it.parent.facility_name }}</td>
                <td v-if="showCoaching" class="px-4 py-3 text-slate-300">—</td>
                <td class="px-4 py-3 text-slate-600">{{ it.parent.customer_name || '—' }}</td>
                <td class="px-4 py-3">
                  <a v-if="waLink(it.parent.customer_phone)" :href="waLink(it.parent.customer_phone)" target="_blank" rel="noopener" @click.stop class="text-emerald-600 hover:underline whitespace-nowrap inline-flex items-center gap-1"><WaIcon /> {{ it.parent.customer_phone }}</a>
                  <span v-else class="text-slate-400">—</span>
                </td>
                <td class="px-4 py-3 text-right font-medium">{{ rupiah(it.parent.order_total) }}</td>
                <td class="px-4 py-3 text-right" :class="it.parent.order_due > 0 ? 'text-amber-600 font-medium' : 'text-slate-400'">{{ rupiah(it.parent.order_due) }}</td>
                <td class="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">{{ fmtPay(it.parent.dp_at) }}</td>
                <td class="px-4 py-3 whitespace-nowrap text-xs" :class="it.parent.paid_off_at ? 'text-emerald-600' : 'text-slate-400'">{{ fmtPay(it.parent.paid_off_at) }}</td>
                <td class="px-4 py-3 text-center"><span :class="statusClass(it.parent.payment_status)" class="text-xs rounded-full px-2 py-0.5">{{ statusLabel(it.parent.payment_status) }}</span></td>
                <td class="px-4 py-3 text-right whitespace-nowrap">
                  <button @click.stop="openDetail(it.parent)" class="text-brand-600 text-xs hover:underline mr-2">Detail</button>
                  <button v-if="canDelete(it.parent)" @click.stop="deleteBooking(it.parent)" class="text-red-500 text-xs hover:text-red-700">Hapus</button>
                </td>
              </tr>
              <!-- rincian tanggal (saat dibuka) — TANPA ulang uang -->
              <template v-if="it.type === 'group' && openOrders.has(it.order_id)">
                <tr v-for="c in it.children" :key="c.id" class="border-t bg-slate-50/30 text-sm">
                  <td class="px-4 py-2 pl-10 text-slate-600">{{ fmtDate(c.booking_date) }}</td>
                  <td class="px-4 py-2 text-slate-600">{{ c.start_time }}–{{ c.end_time }}</td>
                  <td class="px-4 py-2 text-slate-500">{{ c.facility_name }}</td>
                  <td :colspan="showCoaching ? 10 : 9" class="px-4 py-2"></td>
                </tr>
              </template>
            </template>
          </tbody>
        </table>
      </div>
    </div>
    </template>

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

          <button v-if="canReschedule && detail.status !== 'void'" @click="rescheduleOrder = detail"
            class="mt-5 w-full py-2.5 rounded-lg bg-teal-600 hover:bg-teal-700 text-white text-sm font-medium">
            📅 Reschedule Booking
          </button>
          <button v-if="detail.status === 'open' || detail.status === 'partial'" @click="cancelBooking"
            class="mt-2 w-full py-2.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-medium">
            Batalkan Booking (No-show) — DP hangus
          </button>
        </template>
      </div>
    </div>

    <!-- Reschedule booking (manajer) -->
    <RescheduleDialog v-if="rescheduleOrder" :order="rescheduleOrder" :venue-id="detailVenueId"
      @close="rescheduleOrder = null" @done="onRescheduled" />
  </div>
</template>
