<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { usePosStore } from '../stores/pos'
import PaymentDialog from '../components/PaymentDialog.vue'
import ReceiptDialog from '../components/ReceiptDialog.vue'
import CloseShiftDialog from '../components/CloseShiftDialog.vue'
import BookingDialog from '../components/BookingDialog.vue'
import SettlementDialog from '../components/SettlementDialog.vue'

const pos = usePosStore()
const router = useRouter()

const loading = ref(true)
const openingCash = ref('')
const openingBusy = ref(false)
const showPayment = ref(false)
const showReceipt = ref(false)
const showClose = ref(false)
const showBooking = ref(false)
const showSettle = ref(false)
const lastResult = ref(null)
const toast = ref('')

onMounted(async () => {
  try {
    await pos.fetchMe()
    await pos.fetchProducts()
  } catch (e) {
    /* interceptor 401 redirect */
  } finally {
    loading.value = false
  }
})

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
  try {
    const result = await pos.checkout(payload.method, {
      amount: payload.amount,
      reference: payload.reference,
    })
    lastResult.value = result
    showPayment.value = false
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
  <div class="min-h-full flex flex-col">
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
        <button v-if="pos.openShift" @click="showClose = true"
          class="text-xs bg-white/10 hover:bg-white/20 rounded-lg px-3 py-1.5">Tutup Shift</button>
        <button @click="logout" class="text-xs bg-white/10 hover:bg-white/20 rounded-lg px-3 py-1.5">Keluar</button>
      </div>
    </header>

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
        <!-- Mode booking lapangan (venue punya lapangan) -->
        <div v-if="pos.bookingEnabled" class="grid grid-cols-2 gap-2 mb-3">
          <button @click="showBooking = true"
            class="py-2.5 rounded-xl bg-brand-50 hover:bg-brand-100 text-brand-700 font-medium border border-brand-100 flex items-center justify-center gap-2">
            🏟️ Booking
          </button>
          <button @click="showSettle = true"
            class="py-2.5 rounded-xl bg-amber-50 hover:bg-amber-100 text-amber-700 font-medium border border-amber-100 flex items-center justify-center gap-2">
            💰 Pelunasan
          </button>
        </div>
        <!-- Mode tiketing (venue tanpa lapangan, mis. waterpark) -->
        <div v-else class="mb-3 py-2.5 rounded-xl bg-brand-50 text-brand-700 font-medium border border-brand-100 text-center">
          🎟️ Penjualan Tiket — pilih tiket di bawah
        </div>
        <p v-if="pos.products.length === 0" class="text-center text-slate-400 mt-6 text-sm">
          {{ pos.bookingEnabled ? 'Belum ada produk untuk venue ini.' : 'Belum ada tiket/produk. Tambahkan di admin (menu Produk).' }}
        </p>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          <button
            v-for="p in pos.products"
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
                <span v-if="it.item_type === 'booking'" class="text-brand-600">🏟️ </span>{{ it.name }}
              </p>
              <p class="text-xs text-slate-400">
                <template v-if="it.item_type === 'booking'">{{ it.quantity }} jam × {{ rupiah(it.unit_price) }}</template>
                <template v-else>{{ rupiah(it.unit_price) }}</template>
              </p>
              <p v-if="it.promo" class="text-[10px] text-amber-600">🎉 {{ it.promo.label }}</p>
            </div>
            <div v-if="it.item_type === 'product'" class="flex items-center gap-1.5">
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
    <PaymentDialog v-if="showPayment" :total="pos.total" @close="showPayment = false" @pay="onPay" />
    <ReceiptDialog v-if="showReceipt && lastResult" :order="lastResult.order" :payment="lastResult.payment"
      :terminal="pos.terminal" @close="showReceipt = false" />
    <CloseShiftDialog v-if="showClose" :shift="pos.openShift" @close="showClose = false" @submit="onCloseShift" />
    <BookingDialog v-if="showBooking" @close="showBooking = false" @added="flash('Booking ditambahkan ke keranjang')" />
    <SettlementDialog v-if="showSettle" @close="showSettle = false" @paid="onSettlePaid" />

    <!-- Toast -->
    <div v-if="toast" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">
      {{ toast }}
    </div>
  </div>
</template>
