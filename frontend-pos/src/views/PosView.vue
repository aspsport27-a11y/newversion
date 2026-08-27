<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePosStore } from '../stores/pos'
import { useToastStore } from '../stores/toast'
import { stationClock, playAlarmBeep } from '../utils/stationClock'
import PaymentDialog from '../components/PaymentDialog.vue'
import QrisDialog from '../components/QrisDialog.vue'
import ReceiptDialog from '../components/ReceiptDialog.vue'
import CloseShiftDialog from '../components/CloseShiftDialog.vue'
import BookingDialog from '../components/BookingDialog.vue'
import OpenPriceDialog from '../components/OpenPriceDialog.vue'
import OpenBillDialog from '../components/OpenBillDialog.vue'
import MemberBookingDialog from '../components/MemberBookingDialog.vue'
import SettlementDialog from '../components/SettlementDialog.vue'
import AbsenDialog from '../components/AbsenDialog.vue'
import StationStartDialog from '../components/StationStartDialog.vue'
import StationReservationDialog from '../components/StationReservationDialog.vue'
import StationSessionDialog from '../components/StationSessionDialog.vue'
import CategoryReportDialog from '../components/CategoryReportDialog.vue'

const pos = usePosStore()
const router = useRouter()
const toastStore = useToastStore()
const showAbsen = ref(false)
const showCategoryReport = ref(false)

const loading = ref(true)
const openingCash = ref('')
const openingBusy = ref(false)
const showPayment = ref(false)
const showReceipt = ref(false)
const showClose = ref(false)
const showBooking = ref(false)

// ---- Open Bill (bon terbuka) ----
const showOpenBills = ref(false)
const activeBill = ref(null)   // bill yang sedang ditambah item-nya
const draftBill = ref(null)    // bill untuk cetak sementara
async function doOpenBill() {
  if (!pos.cart.length) return
  const name = window.prompt('Nama untuk bill ini (mis. nama customer / meja):', pos.customerName || '')
  if (name === null) return
  pos.customerName = (name || '').trim()
  try {
    await pos.openBill()
    pos.clearCart()
    flash('Bill dibuka — bisa ditambah item lewat "Bill Terbuka".')
  } catch (e) { flash(e?.response?.data?.message || 'Gagal membuka bill') }
}
function onBillAddItem(order) {
  activeBill.value = order
  showOpenBills.value = false
  flash(`Pilih item, lalu tekan "Tambahkan ke Bill".`)
}
async function doAddToBill() {
  if (!pos.cart.length || !activeBill.value) return
  try {
    await pos.addItemsToBill(activeBill.value.id)
    pos.clearCart()
    flash('Item ditambahkan ke bill.')
    activeBill.value = null
  } catch (e) { flash(e?.response?.data?.message || 'Gagal menambah item') }
}
function onBillPaid(res) {
  showOpenBills.value = false
  lastResult.value = res
  showReceipt.value = true
}

// produk harga terbuka (mis. Parkir) → minta nominal dulu
const openPriceProduct = ref(null)
function onProductTap(p) {
  if (p.open_price) openPriceProduct.value = p
  else pos.addProduct(p)
}
function onOpenPriceAdd(amount) {
  pos.addOpenPriceProduct(openPriceProduct.value, amount)
  openPriceProduct.value = null
}
const showMember = ref(false)
const showSettle = ref(false)
const lastResult = ref(null)

const startStation = ref(null)
const showStationResv = ref(false)
const sessionStation = ref(null)
const pendingStationOrder = ref(null)

// --- pencarian & filter kategori F&B (biar tak perlu scroll daftar panjang) ---
const fnbSearch = ref('')
const fnbCategory = ref('')
const fnbCategories = computed(() => {
  const set = new Set()
  for (const p of pos.fnbProducts) if (p.category_name) set.add(p.category_name)
  return [...set].sort()
})
const filteredFnb = computed(() => {
  let list = pos.fnbProducts
  if (fnbCategory.value) list = list.filter((p) => p.category_name === fnbCategory.value)
  const q = fnbSearch.value.trim().toLowerCase()
  if (q) list = list.filter((p) => p.name.toLowerCase().includes(q))
  return list
})

onMounted(async () => {
  try {
    await pos.fetchMe()
    await pos.fetchProducts()
    try { await pos.fetchStations() } catch (_) { /* venue tanpa station gaming */ }
  } catch (e) {
    /* interceptor 401 redirect */
  } finally {
    loading.value = false
  }
})

let stationPoll = null
onMounted(() => { stationPoll = setInterval(() => { if (pos.hasStations && !sessionStation.value) pos.fetchStations() }, 5000) })
onUnmounted(() => clearInterval(stationPoll))

// jam & harga berjalan tiap detik di kartu grid station (bukan cuma di
// dalam dialog sesi) — dipakai jg utk cek alarm waktu habis
const nowTick = ref(Date.now())
let clockTimer = null
onMounted(() => { clockTimer = setInterval(() => (nowTick.value = Date.now()), 1000) })
onUnmounted(() => clearInterval(clockTimer))

function stationClockFor(s) {
  return s.status === 'ongoing' ? stationClock(s.session, nowTick.value, s.hourly_rate) : null
}

// alarm bunyi begitu ada station yg waktunya habis (overtime), diulang tiap
// 60 detik selama masih overtime & belum ditambah waktu/di-stop — spy kasir
// pasti sadar tapi tak berisik terus-menerus tiap detik
const lastAlarmAt = {}
watch(nowTick, () => {
  for (const s of pos.stations) {
    const c = stationClockFor(s)
    if (!c || !c.isOvertime) { delete lastAlarmAt[s.id]; continue }
    const last = lastAlarmAt[s.id]
    if (!last || Date.now() - last >= 60000) {
      playAlarmBeep()
      lastAlarmAt[s.id] = Date.now()
    }
  }
})

function openStation(s) {
  if (s.status === 'ongoing') sessionStation.value = s
  else startStation.value = s
}
// station dikelompokkan per tier (rapi walau banyak station)
const TIER_LABEL = { reguler: 'Reguler', vip: 'VIP', simulator: 'Simulator' }
const stationsByTier = computed(() => {
  const g = {}
  for (const s of pos.stations) (g[s.tier || 'reguler'] ||= []).push(s)
  return g
})
// PRABAYAR station: order dgn sisa tagihan → ke PaymentDialog; kalau lunas → selesai
const sessionToOpenAfterPay = ref(null) // station id yg dibuka lagi setelah bayar
function payStationOrder(order) {
  if (order && Number(order.amount_due) > 0) {
    pendingStationOrder.value = order
    showPayment.value = true
    return true
  }
  return false
}
function openSessionAfterPay() {
  const sid = sessionToOpenAfterPay.value
  sessionToOpenAfterPay.value = null
  if (sid == null) return
  const s = pos.stations.find((x) => x.id === sid)
  if (s) sessionStation.value = s // masuk ke dialog sesi (state 'belum main / Play')
}
function onStationStarted(res) {
  startStation.value = null
  sessionToOpenAfterPay.value = res.session?.station_id ?? null
  if (!payStationOrder(res.order)) { pos.fetchStations().then(openSessionAfterPay) }
}
// Reservasi dibuat → langsung minta bayar (DP/lunas) lewat PaymentDialog
function onReservationCreated(res) {
  showStationResv.value = false
  payStationOrder({ ...res.order, amount_due: res.order.total_amount })
}
// Customer datang & unit ditentukan → buka dialog sesi (state 'belum main/Play').
// Uangnya sudah menempel di order reservasi, jadi tak ada tagihan baru di sini.
function onReservationStarted(res) {
  showStationResv.value = false
  sessionToOpenAfterPay.value = res.session?.station_id ?? null
  pos.fetchStations().then(openSessionAfterPay)
}
function onStationPayOrder(order) {
  sessionToOpenAfterPay.value = sessionStation.value?.id ?? null
  sessionStation.value = null
  if (!payStationOrder(order)) { pos.fetchStations().then(openSessionAfterPay) }
}
function onStationStopped(result) {
  sessionStation.value = null
  if (!payStationOrder(result.order)) {
    // durasi sudah lunas & tak ada F&B/add-on → sesi selesai tanpa bayar lagi
    flash('Sesi selesai — sudah lunas.')
    pos.fetchStations()
  }
}
// booking member: order sudah dibuat di server → langsung ke pembayaran
// (reuse jalur pendingStationOrder = "order yg sudah ada, tinggal bayar")
function onMemberCreated({ order, booked, skipped }) {
  showMember.value = false
  pendingStationOrder.value = order
  showPayment.value = true
  if (skipped && skipped.length) {
    flash(`${booked.length} tanggal dibooking, ${skipped.length} dilewati (bentrok).`)
  } else {
    flash(`${booked.length} tanggal member dibooking.`)
  }
}
async function onPayStation(payload) {
  try {
    const res = payload.splits
      ? await pos.settleSplit(pendingStationOrder.value.id, payload.splits)
      : await pos.settle(pendingStationOrder.value.id, payload.method, payload.amount, payload.reference, payload.proof_image)
    showPayment.value = false
    pendingStationOrder.value = null
    if (openQrisIfNeeded(res)) return
    await pos.fetchProducts()
    // sesi station (start/topup/add-on) → kembali ke dialog sesi, bukan struk
    if (sessionToOpenAfterPay.value != null) { await pos.fetchStations(); openSessionAfterPay(); return }
    lastResult.value = res
    showReceipt.value = true
  } catch (e) {
    flash(e?.response?.data?.message || 'Pembayaran gagal')
  }
}

// --- QRIS dinamis (BRIAPI) ---
// Kalau server berhasil membuat QR, tahan struk dulu: uang belum masuk sampai
// bank mengonfirmasi. Struk baru dicetak setelah status jadi 'paid'.
const qrisPayment = ref(null)   // { id, amount }
const qrisResult = ref(null)    // hasil transaksi yg ditahan sampai lunas

function openQrisIfNeeded(result) {
  const p = result?.payment
  // qr_expires_at hanya terisi kalau BRIAPI aktif & QR berhasil dibuat.
  // Kalau integrasi mati, jatuh ke perilaku lama (pending, konfirmasi manual).
  if (p && p.method === 'qris' && p.status === 'pending' && p.qr_expires_at) {
    qrisPayment.value = { id: p.id, amount: p.amount }
    qrisResult.value = result
    return true
  }
  return false
}

async function onQrisPaid() {
  const res = qrisResult.value
  if (res?.payment) res.payment.status = 'paid'
  qrisPayment.value = null
  qrisResult.value = null
  lastResult.value = res
  showReceipt.value = true
  pos.clearCart()
  await pos.fetchProducts()
  await pos.fetchMe()
}

function onQrisClose() {
  // Transaksi tetap tercatat pending di server — bisa dilunasi lewat menu
  // "Order Belum Bayar" kalau customer menyusul membayar.
  qrisPayment.value = null
  qrisResult.value = null
  pos.clearCart()
  flash('Transaksi QRIS tersimpan sebagai belum lunas.')
}

function rupiah(n) {
  return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
}
function flash(msg) {
  toastStore.show(msg)
}

async function submitOpenShift() {
  openingBusy.value = true
  try {
    await pos.doOpenShift(Number(openingCash.value) || 0)
    openingCash.value = ''
  } catch (e) {
    flash(e?.response?.data?.message || 'Gagal membuka shift')
  } finally {
    openingBusy.value = false
  }
}

async function onPay(payload) {
  if (pendingStationOrder.value) return onPayStation(payload)
  try {
    const result = await pos.checkout(payload.method, {
      amount: payload.amount,
      reference: payload.reference,
      proof_image: payload.proof_image,
      splits: payload.splits,
    })
    showPayment.value = false
    if (openQrisIfNeeded(result)) return
    lastResult.value = result
    showReceipt.value = true
    pos.clearCart()
    await pos.fetchProducts()
    await pos.fetchMe()
  } catch (e) {
    flash(e?.response?.data?.message || 'Pembayaran gagal')
  }
}

async function onSettlePaid(result) {
  lastResult.value = result
  showSettle.value = false
  showReceipt.value = true
  await pos.fetchMe()
}

async function onCloseShift(payload) {
  try {
    const shift = await pos.doCloseShift(payload.counted_cash, payload.deposit_amount, payload.notes)
    showClose.value = false
    flash(`Shift ditutup. Selisih: ${rupiah(shift.cash_variance)}`)
  } catch (e) {
    flash(e?.response?.data?.message || 'Gagal menutup shift')
  }
}

function logout() {
  pos.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Header -->
    <header class="h-14 bg-brand-900 text-white flex items-center justify-between px-4 shrink-0">
      <div class="flex items-center gap-3">
        <img src="/asp-logo.png" alt="ASP Sports" class="h-5" style="filter: brightness(0) invert(1)" />
        <div class="leading-tight border-l border-white/20 pl-3">
          <p class="text-sm font-semibold">{{ pos.terminal?.name || 'POS' }}</p>
          <p class="text-[11px] text-brand-100">{{ pos.cashier?.username }} · {{ pos.terminal?.code }}</p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button @click="showCategoryReport = true"
          class="text-xs bg-white/10 hover:bg-white/20 rounded-lg px-3 py-1.5">📊 Laporan</button>
        <button @click="showAbsen = true"
          class="text-xs bg-white/10 hover:bg-white/20 rounded-lg px-3 py-1.5">🕐 Absen</button>
        <button v-if="pos.openShift" @click="showClose = true"
          class="text-xs bg-white/10 hover:bg-white/20 rounded-lg px-3 py-1.5">Tutup Shift</button>
        <button @click="logout" class="text-xs bg-white/10 hover:bg-white/20 rounded-lg px-3 py-1.5">Keluar</button>
      </div>
    </header>

    <AbsenDialog v-if="showAbsen" :terminal-code="pos.terminal?.code || ''" @close="showAbsen = false" />
    <CategoryReportDialog v-if="showCategoryReport" @close="showCategoryReport = false" />

    <div v-if="loading" class="flex-1 grid place-items-center text-slate-400">Memuat…</div>

    <!-- BELUM ADA SHIFT: buka shift -->
    <div v-else-if="!pos.openShift" class="flex-1 grid place-items-center p-4">
      <div class="bg-white rounded-2xl shadow p-6 w-full max-w-sm text-center">
        <div class="text-3xl mb-2">🔓</div>
        <h2 class="text-lg font-bold text-slate-800 mb-1">Buka Shift</h2>
        <p class="text-sm text-slate-500 mb-4">Masukkan saldo awal laci kas.</p>
        <input v-model="openingCash" type="number" inputmode="numeric" placeholder="Saldo awal (Rp)"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-lg text-right outline-none focus:border-brand-500 mb-3" />
        <button @click="submitOpenShift" :disabled="openingBusy"
          class="w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-semibold disabled:opacity-50">
          {{ openingBusy ? 'Membuka…' : 'Mulai Shift' }}
        </button>
      </div>
    </div>

    <!-- POS UTAMA -->
    <div v-else class="flex-1 flex flex-col lg:flex-row min-h-0">
      <!-- Produk -->
      <div class="flex-1 overflow-auto p-3">
        <!-- Booking lapangan (venue punya lapangan) + Pelunasan (order belum
             lunas apa pun jenisnya — booking, station, dll — jadi tetap
             ditampilkan meski venue tak punya lapangan, mis. venue Station
             Gaming murni, supaya order yg sempat dibuat tapi dialog
             pembayarannya ditutup tanpa bayar tak "hilang" dr jangkauan kasir) -->
        <div v-if="pos.bookingEnabled || pos.hasStations" class="flex flex-wrap gap-2 mb-3">
          <button v-if="pos.bookingEnabled" @click="showBooking = true"
            class="flex-1 min-w-[30%] py-2.5 rounded-xl bg-brand-50 hover:bg-brand-100 text-brand-700 font-medium border border-brand-100 flex items-center justify-center gap-2">
            🏟️ Booking
          </button>
          <button v-if="pos.bookingEnabled" @click="showMember = true"
            class="flex-1 min-w-[30%] py-2.5 rounded-xl bg-purple-50 hover:bg-purple-100 text-purple-700 font-medium border border-purple-100 flex items-center justify-center gap-2">
            🗓️ Member
          </button>
          <button v-if="pos.hasStations" @click="showStationResv = true"
            class="flex-1 min-w-[30%] py-2.5 rounded-xl bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-medium border border-indigo-100 flex items-center justify-center gap-2">
            📅 Reservasi
          </button>
          <button @click="showSettle = true"
            class="flex-1 min-w-[30%] py-2.5 rounded-xl bg-amber-50 hover:bg-amber-100 text-amber-700 font-medium border border-amber-100 flex items-center justify-center gap-2">
            💰 Pelunasan
          </button>
          <button @click="showOpenBills = true"
            class="flex-1 min-w-[30%] py-2.5 rounded-xl bg-teal-50 hover:bg-teal-100 text-teal-700 font-medium border border-teal-100 flex items-center justify-center gap-2">
            🧾 Bill Terbuka
          </button>
        </div>

        <!-- Reservasi hari ini — biar kasir tahu tanpa membuka dialog dulu -->
        <button v-if="pos.reservationsToday.length" @click="showStationResv = true"
          class="w-full text-left bg-indigo-50 border border-indigo-200 rounded-xl px-3 py-2 mb-3 hover:bg-indigo-100">
          <p class="text-xs font-semibold text-indigo-700 mb-0.5">
            📅 {{ pos.reservationsToday.length }} reservasi hari ini
          </p>
          <p v-for="r in pos.reservationsToday.slice(0, 3)" :key="r.id" class="text-xs text-indigo-600">
            {{ r.start_time }}–{{ r.end_time }} · {{ r.station_type }}<span v-if="r.customer_name"> · {{ r.customer_name }}</span>
          </p>
          <p v-if="pos.reservationsToday.length > 3" class="text-xs text-indigo-400">
            +{{ pos.reservationsToday.length - 3 }} lagi — ketuk untuk lihat semua
          </p>
        </button>

        <!-- Station Gaming (arena esport) — dikelompokkan per tier -->
        <div v-if="pos.hasStations" class="mb-4">
          <p class="text-xs font-semibold text-slate-400 mb-1.5">🎮 STATION</p>
          <div v-for="(list, tier) in stationsByTier" :key="tier" class="mb-3">
            <p class="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1">{{ TIER_LABEL[tier] || tier }} <span class="text-slate-300 font-normal">· {{ list.length }}</span></p>
            <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
              <button v-for="s in list" :key="s.id" @click="openStation(s)"
                class="rounded-xl border p-3 text-left active:scale-95 transition"
                :class="s.status === 'ongoing' ? (stationClockFor(s).isOvertime ? 'bg-red-50 border-red-300' : 'bg-emerald-50 border-emerald-200') : 'bg-white hover:border-brand-400'">
                <div class="flex justify-between items-start">
                  <p class="font-semibold text-slate-800 text-sm">{{ s.name }}</p>
                  <span class="text-[10px] rounded px-1.5 py-0.5"
                    :class="s.status === 'ongoing' ? (stationClockFor(s).isOvertime ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700') : 'bg-slate-100 text-slate-500'">
                    {{ s.status === 'ongoing' ? (stationClockFor(s).isOvertime ? 'LEWAT WAKTU' : 'ONGOING') : 'READY' }}
                  </span>
                </div>
                <template v-if="s.status === 'ongoing'">
                  <p class="text-xs text-slate-600 font-medium mt-1 truncate">{{ s.session.customer_name || 'Tanpa nama' }}</p>
                  <p class="font-mono text-sm font-bold mt-0.5" :class="stationClockFor(s).isOvertime ? 'text-red-600' : 'text-emerald-700'">{{ stationClockFor(s).clockLabel }}</p>
                  <p class="text-xs text-brand-700 font-semibold">{{ rupiah(stationClockFor(s).runningTotal) }}</p>
                </template>
                <p v-else class="text-xs text-slate-400 mt-1">{{ rupiah(s.today_rate ?? s.hourly_rate) }}/jam</p>
              </button>
            </div>
          </div>
        </div>

        <!-- Tiket (klik = masuk keranjang, harga hari ini otomatis) -->
        <div v-if="pos.tickets.length" class="mb-4">
          <p class="text-xs font-semibold text-slate-400 mb-1.5">🎟️ TIKET MASUK</p>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
            <button v-for="t in pos.tickets" :key="t.id" @click="pos.addTicket(t)"
              class="py-3 px-3 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-left active:scale-95 transition">
              <p class="font-semibold text-sm leading-tight">{{ t.name }}</p>
              <p class="font-bold mt-0.5">{{ rupiah(t.effective_price ?? t.price) }}</p>
            </button>
          </div>
        </div>

        <p v-if="pos.products.length === 0" class="text-center text-slate-400 mt-6 text-sm">
          Belum ada tiket/produk untuk venue ini. Tambahkan di admin.
        </p>
        <div v-if="pos.fnbProducts.length">
          <p class="text-xs font-semibold text-slate-400 mb-1.5">🍔 F&amp;B</p>
          <input
            v-model="fnbSearch"
            type="text"
            placeholder="Cari produk..."
            class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm mb-2 outline-none focus:border-brand-500"
          />
          <div v-if="fnbCategories.length" class="flex gap-1.5 overflow-x-auto pb-2 mb-1 -mx-0.5 px-0.5">
            <button
              @click="fnbCategory = ''"
              :class="['shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition', fnbCategory === '' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200']"
            >Semua</button>
            <button
              v-for="c in fnbCategories"
              :key="c"
              @click="fnbCategory = c"
              :class="['shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition', fnbCategory === c ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200']"
            >{{ c }}</button>
          </div>
        </div>
        <p v-if="pos.fnbProducts.length && !filteredFnb.length" class="text-center text-slate-400 text-sm py-4">
          Tidak ada produk yang cocok.
        </p>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          <button
            v-for="p in filteredFnb"
            :key="p.id"
            @click="onProductTap(p)"
            :disabled="!p.open_price && p.track_stock && p.stock_qty <= 0"
            class="bg-white rounded-xl border p-3 text-left hover:border-brand-400 active:scale-95 transition disabled:opacity-40"
          >
            <p class="font-medium text-slate-800 text-sm leading-tight">{{ p.name }}</p>
            <p v-if="p.open_price" class="text-brand-700 font-semibold text-xs mt-1">Nominal diketik ✏️</p>
            <template v-else>
            <p v-if="p.promo && p.effective_price < p.price" class="mt-1">
              <span class="text-brand-700 font-bold">{{ rupiah(p.effective_price) }}</span>
              <span class="text-[11px] text-slate-400 line-through ml-1">{{ rupiah(p.price) }}</span>
            </p>
            <p v-else class="text-brand-700 font-bold mt-1">{{ rupiah(p.price) }}</p>
            </template>
            <p v-if="p.promo" class="text-[10px] text-amber-700 bg-amber-50 rounded px-1.5 py-0.5 mt-1 inline-block">🎉 {{ p.promo.label }}</p>
            <p v-if="p.track_stock" class="text-[11px] text-slate-400 mt-0.5">stok: {{ p.stock_qty }}</p>
          </button>
        </div>
      </div>

      <!-- Keranjang -->
      <div class="w-full lg:w-80 bg-white border-t lg:border-t-0 lg:border-l flex flex-col shrink-0 max-h-[45vh] lg:max-h-none">
        <div class="p-3 border-b font-semibold text-slate-700 flex justify-between items-center">
          <span>Keranjang</span>
          <button v-if="pos.cart.length" @click="pos.clearCart()" class="text-xs text-red-500">Kosongkan</button>
        </div>

        <div class="flex-1 overflow-auto p-3 space-y-2">
          <p v-if="!pos.cart.length" class="text-center text-slate-400 text-sm mt-6">Keranjang kosong</p>
          <div v-for="it in pos.cart" :key="it.uid" class="flex items-center gap-2">
            <div class="flex-1 min-w-0">
              <p class="text-sm text-slate-700 truncate">
                <span v-if="it.item_type === 'booking'" class="text-brand-600">🏟️ </span><span v-else-if="it.item_type === 'ticket'" class="text-brand-600">🎟️ </span>{{ it.name }}
              </p>
              <p class="text-xs text-slate-400">
                <template v-if="it.item_type === 'booking'">{{ it.quantity }} jam × {{ rupiah(it.unit_price) }}</template>
                <template v-else>{{ rupiah(it.unit_price) }}</template>
              </p>
              <p v-if="it.coaching_label" class="text-[10px] text-teal-600">🎾 {{ it.coaching_label }} · {{ rupiah(it.coaching_preview) }}</p>
              <p v-if="it.promo" class="text-[10px] text-amber-600">🎉 {{ it.promo.label }}</p>
            </div>
            <div v-if="it.item_type === 'product' || it.item_type === 'ticket'" class="flex items-center gap-1.5">
              <button @click="pos.decQty(it)" class="h-7 w-7 rounded bg-slate-100 text-slate-600 font-bold">−</button>
              <input :value="it.quantity" @change="pos.setQty(it, $event.target.value)" type="number" min="1" inputmode="numeric"
                class="w-12 h-7 text-center text-sm rounded border border-slate-200 outline-none focus:border-brand-500" />
              <button @click="pos.incQty(it)" class="h-7 w-7 rounded bg-slate-100 text-slate-600 font-bold">+</button>
            </div>
            <button v-else @click="pos.removeItem(it)" class="h-7 w-7 rounded bg-slate-100 text-slate-400 shrink-0">✕</button>
            <span class="w-16 text-right text-sm font-medium">{{ rupiah(pos.lineTotal(it)) }}</span>
          </div>
        </div>

        <div class="p-3 border-t space-y-2">
          <div class="flex items-center justify-between text-sm">
            <span class="text-slate-500">Diskon</span>
            <div class="flex items-center gap-1">
              <div class="flex rounded border border-slate-300 overflow-hidden text-xs">
                <button @click="pos.discountType = 'rp'" :class="pos.discountType === 'rp' ? 'bg-brand-600 text-white' : 'bg-white text-slate-500'" class="px-2 py-1 font-medium">Rp</button>
                <button @click="pos.discountType = 'percent'" :class="pos.discountType === 'percent' ? 'bg-brand-600 text-white' : 'bg-white text-slate-500'" class="px-2 py-1 font-medium">%</button>
              </div>
              <input v-model="pos.discount" type="number" inputmode="numeric" placeholder="0"
                :max="pos.discountType === 'percent' ? 100 : undefined"
                class="w-20 rounded border border-slate-300 px-2 py-1 text-right text-sm outline-none focus:border-brand-500" />
            </div>
          </div>
          <div v-if="pos.discountRp > 0" class="flex justify-between text-xs text-amber-600">
            <span>Potongan{{ pos.discountType === 'percent' ? ` (${pos.discount || 0}%)` : '' }}</span>
            <span>- {{ rupiah(pos.discountRp) }}</span>
          </div>
          <div class="flex justify-between font-bold text-lg">
            <span>Total</span><span class="text-brand-700">{{ rupiah(pos.total) }}</span>
          </div>

          <!-- Mode: menambah item ke bill terbuka -->
          <template v-if="activeBill">
            <div class="text-xs bg-teal-50 border border-teal-200 text-teal-800 rounded-lg px-2 py-1.5">
              ➕ Menambah ke bill: <b>{{ activeBill.customer_name || 'Tanpa nama' }}</b>
            </div>
            <button @click="doAddToBill" :disabled="!pos.cart.length"
              class="w-full py-3 rounded-lg bg-teal-600 hover:bg-teal-700 text-white font-semibold disabled:opacity-40">
              Tambahkan ke Bill
            </button>
            <button @click="activeBill = null" class="w-full py-1.5 text-xs text-slate-500 hover:text-slate-700">Batal menambah</button>
          </template>

          <!-- Mode normal: bayar langsung / buka bill -->
          <template v-else>
            <button @click="showPayment = true" :disabled="!pos.cart.length"
              class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-40">Bayar</button>
            <button @click="doOpenBill" :disabled="!pos.cart.length"
              class="w-full py-2 rounded-lg bg-teal-50 hover:bg-teal-100 text-teal-700 font-medium border border-teal-200 disabled:opacity-40">🧾 Buka Bill (bayar nanti)</button>
          </template>
        </div>
      </div>
    </div>

    <!-- Dialogs -->
    <PaymentDialog v-if="showPayment" :total="pendingStationOrder ? (pendingStationOrder.amount_due ?? pendingStationOrder.total_amount) : pos.total"
      :qris-dynamic="pos.qrisDynamic"
      @close="showPayment = false; pendingStationOrder = null" @pay="onPay" />
    <QrisDialog v-if="qrisPayment" :payment-id="qrisPayment.id" :amount="qrisPayment.amount"
      @paid="onQrisPaid" @close="onQrisClose" />
    <OpenPriceDialog v-if="openPriceProduct" :name="openPriceProduct.name"
      @add="onOpenPriceAdd" @close="openPriceProduct = null" />
    <ReceiptDialog v-if="showReceipt && lastResult" :order="lastResult.order" :payment="lastResult.payment"
      :terminal="pos.terminal" @close="showReceipt = false" />
    <CloseShiftDialog v-if="showClose" :shift="pos.openShift" @close="showClose = false" @submit="onCloseShift" />
    <BookingDialog v-if="showBooking" @close="showBooking = false" @added="flash('Booking ditambahkan ke keranjang')" />
    <MemberBookingDialog v-if="showMember" @close="showMember = false" @created="onMemberCreated" />
    <StationReservationDialog v-if="showStationResv" @close="showStationResv = false"
      @created="onReservationCreated" @started="onReservationStarted" />
    <SettlementDialog v-if="showSettle" @close="showSettle = false" @paid="onSettlePaid" />
    <OpenBillDialog v-if="showOpenBills" @close="showOpenBills = false"
      @add-item="onBillAddItem" @paid="onBillPaid" @print="draftBill = $event" />
    <ReceiptDialog v-if="draftBill" :order="draftBill" :terminal="pos.terminal" draft @close="draftBill = null" />
    <StationStartDialog v-if="startStation" :station="startStation" @close="startStation = null"
      @started="onStationStarted" />
    <StationSessionDialog v-if="sessionStation" :station="sessionStation" @close="sessionStation = null; pos.fetchStations()"
      @stopped="onStationStopped" @pay-order="onStationPayOrder" />
  </div>
</template>
