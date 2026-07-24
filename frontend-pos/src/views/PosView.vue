<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePosStore } from '../stores/pos'
import { stationClock, playAlarmBeep } from '../utils/stationClock'
import PaymentDialog from '../components/PaymentDialog.vue'
import QrisDialog from '../components/QrisDialog.vue'
import ReceiptDialog from '../components/ReceiptDialog.vue'
import CloseShiftDialog from '../components/CloseShiftDialog.vue'
import BookingDialog from '../components/BookingDialog.vue'
import MemberBookingDialog from '../components/MemberBookingDialog.vue'
import SettlementDialog from '../components/SettlementDialog.vue'
import AbsenDialog from '../components/AbsenDialog.vue'
import StationStartDialog from '../components/StationStartDialog.vue'
import StationSessionDialog from '../components/StationSessionDialog.vue'
import CategoryReportDialog from '../components/CategoryReportDialog.vue'

const pos = usePosStore()
const router = useRouter()
const showAbsen = ref(false)
const showCategoryReport = ref(false)

const loading = ref(true)
const openingCash = ref('')
const openingBusy = ref(false)
const showPayment = ref(false)
const showReceipt = ref(false)
const showClose = ref(false)
const showBooking = ref(false)
const showMember = ref(false)
const showSettle = ref(false)
const lastResult = ref(null)
const toast = ref('')

const startStation = ref(null)
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
function onStationStopped(result) {
  sessionStation.value = null
  pendingStationOrder.value = result.order
  showPayment.value = true
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
    const res = await pos.settle(pendingStationOrder.value.id, payload.method, payload.amount, payload.reference, payload.proof_image)
    showPayment.value = false
    pendingStationOrder.value = null
    if (openQrisIfNeeded(res)) return
    lastResult.value = res
    showReceipt.value = true
    await pos.fetchProducts()
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
  toast.value = msg
  setTimeout(() => (toast.value = ''), 2500)
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
          <button @click="showSettle = true"
            class="flex-1 min-w-[30%] py-2.5 rounded-xl bg-amber-50 hover:bg-amber-100 text-amber-700 font-medium border border-amber-100 flex items-center justify-center gap-2">
            💰 Pelunasan
          </button>
        </div>

        <!-- Station Gaming (arena esport) -->
        <div v-if="pos.hasStations" class="mb-4">
          <p class="text-xs font-semibold text-slate-400 mb-1.5">🎮 STATION</p>
          <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
            <button v-for="s in pos.stations" :key="s.id" @click="openStation(s)"
              class="rounded-xl border p-3 text-left active:scale-95 transition"
              :class="s.status === 'ongoing' ? (stationClockFor(s).isOvertime ? 'bg-red-50 border-red-300' : 'bg-emerald-50 border-emerald-200') : 'bg-white hover:border-brand-400'">
              <div class="flex justify-between items-start">
                <p class="font-semibold text-slate-800 text-sm">{{ s.name }}</p>
                <span class="text-[10px] rounded px-1.5 py-0.5"
                  :class="s.status === 'ongoing' ? (stationClockFor(s).isOvertime ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700') : 'bg-slate-100 text-slate-500'">
                  {{ s.status === 'ongoing' ? (stationClockFor(s).isOvertime ? 'LEWAT WAKTU' : 'ONGOING') : 'READY' }}
                </span>
              </div>
              <p class="text-[11px] text-slate-400 capitalize mt-0.5">{{ s.tier }}</p>
              <template v-if="s.status === 'ongoing'">
                <p class="text-xs text-slate-600 font-medium mt-1 truncate">{{ s.session.customer_name || 'Tanpa nama' }}</p>
                <p class="font-mono text-sm font-bold mt-0.5" :class="stationClockFor(s).isOvertime ? 'text-red-600' : 'text-emerald-700'">{{ stationClockFor(s).clockLabel }}</p>
                <p class="text-xs text-brand-700 font-semibold">{{ rupiah(stationClockFor(s).runningTotal) }}</p>
              </template>
              <p v-else class="text-xs text-slate-400 mt-1">{{ rupiah(s.hourly_rate) }}/jam</p>
            </button>
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
            @click="pos.addProduct(p)"
            :disabled="p.track_stock && p.stock_qty <= 0"
            class="bg-white rounded-xl border p-3 text-left hover:border-brand-400 active:scale-95 transition disabled:opacity-40"
          >
            <p class="font-medium text-slate-800 text-sm leading-tight">{{ p.name }}</p>
            <p v-if="p.promo && p.effective_price < p.price" class="mt-1">
              <span class="text-brand-700 font-bold">{{ rupiah(p.effective_price) }}</span>
              <span class="text-[11px] text-slate-400 line-through ml-1">{{ rupiah(p.price) }}</span>
            </p>
            <p v-else class="text-brand-700 font-bold mt-1">{{ rupiah(p.price) }}</p>
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
              <p v-if="it.promo" class="text-[10px] text-amber-600">🎉 {{ it.promo.label }}</p>
            </div>
            <div v-if="it.item_type === 'product' || it.item_type === 'ticket'" class="flex items-center gap-1.5">
              <button @click="pos.decQty(it)" class="h-7 w-7 rounded bg-slate-100 text-slate-600 font-bold">−</button>
              <span class="w-6 text-center text-sm">{{ it.quantity }}</span>
              <button @click="pos.incQty(it)" class="h-7 w-7 rounded bg-slate-100 text-slate-600 font-bold">+</button>
            </div>
            <button v-else @click="pos.removeItem(it)" class="h-7 w-7 rounded bg-slate-100 text-slate-400 shrink-0">✕</button>
            <span class="w-16 text-right text-sm font-medium">{{ rupiah(pos.lineTotal(it)) }}</span>
          </div>
        </div>

        <div class="p-3 border-t space-y-2">
          <div class="flex items-center justify-between text-sm">
            <span class="text-slate-500">Diskon</span>
            <input v-model="pos.discount" type="number" inputmode="numeric" placeholder="0"
              class="w-24 rounded border border-slate-300 px-2 py-1 text-right text-sm outline-none focus:border-brand-500" />
          </div>
          <div class="flex justify-between font-bold text-lg">
            <span>Total</span><span class="text-brand-700">{{ rupiah(pos.total) }}</span>
          </div>
          <button
            @click="showPayment = true"
            :disabled="!pos.cart.length"
            class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-40"
          >Bayar</button>
        </div>
      </div>
    </div>

    <!-- Dialogs -->
    <PaymentDialog v-if="showPayment" :total="pendingStationOrder ? pendingStationOrder.total_amount : pos.total"
      @close="showPayment = false; pendingStationOrder = null" @pay="onPay" />
    <QrisDialog v-if="qrisPayment" :payment-id="qrisPayment.id" :amount="qrisPayment.amount"
      @paid="onQrisPaid" @close="onQrisClose" />
    <ReceiptDialog v-if="showReceipt && lastResult" :order="lastResult.order" :payment="lastResult.payment"
      :terminal="pos.terminal" @close="showReceipt = false" />
    <CloseShiftDialog v-if="showClose" :shift="pos.openShift" @close="showClose = false" @submit="onCloseShift" />
    <BookingDialog v-if="showBooking" @close="showBooking = false" @added="flash('Booking ditambahkan ke keranjang')" />
    <MemberBookingDialog v-if="showMember" @close="showMember = false" @created="onMemberCreated" />
    <SettlementDialog v-if="showSettle" @close="showSettle = false" @paid="onSettlePaid" />
    <StationStartDialog v-if="startStation" :station="startStation" @close="startStation = null"
      @started="startStation = null; pos.fetchStations()" />
    <StationSessionDialog v-if="sessionStation" :station="sessionStation" @close="sessionStation = null; pos.fetchStations()"
      @stopped="onStationStopped" />

    <!-- Toast -->
    <div v-if="toast" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">
      {{ toast }}
    </div>
  </div>
</template>
