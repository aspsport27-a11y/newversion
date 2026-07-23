<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { usePosStore } from '../stores/pos'
import { stationClock } from '../utils/stationClock'

const props = defineProps({ station: Object })
const emit = defineEmits(['close', 'stopped'])
const pos = usePosStore()

const session = computed(() => props.station.session)
const now = ref(Date.now())
let timer = null
onMounted(() => { timer = setInterval(() => (now.value = Date.now()), 1000) })
onUnmounted(() => clearInterval(timer))

// hitungan jam & harga sesi — sama persis dgn yg dipakai di grid station
// (PosView), lihat utils/stationClock.js utk penjelasan lengkap logikanya
const clock = computed(() => stationClock(session.value, now.value, props.station.hourly_rate))
const timeCharge = computed(() => clock.value.timeCharge)
const topupCharge = computed(() => clock.value.topupCharge)
const addonCharge = computed(() => clock.value.addonCharge)
const allocatedMinutes = computed(() => clock.value.allocatedMinutes)
const billableMinutes = computed(() => clock.value.billableMinutes)
const isCountdown = computed(() => clock.value.isCountdown)
const clockLabel = computed(() => clock.value.clockLabel)
const isOvertime = computed(() => clock.value.isOvertime)

function rupiah(n) { return 'Rp ' + Math.round(Number(n) || 0).toLocaleString('id-ID') }

// --- tambah waktu (topup) ---
const showTopup = ref(false)
const topupDuration = ref(60)
const topupDiscount = ref(0)
const topupTotalOverride = ref(null) // null = pakai hitungan otomatis; diisi kalau kasir override manual
const busy = ref(false)
const err = ref('')

// nominal langsung muncul otomatis dr durasi × tarif/jam, dikurangi diskon —
// kasir masih bisa override manual (mis. ada nego harga) via topupTotalOverride
const topupAutoTotal = computed(() => {
  const gross = (Number(topupDuration.value) || 0) / 60 * Number(props.station.hourly_rate)
  return Math.max(0, Math.round((gross - (Number(topupDiscount.value) || 0)) * 100) / 100)
})
const topupTotal = computed({
  get: () => topupTotalOverride.value ?? topupAutoTotal.value,
  set: (v) => { topupTotalOverride.value = v },
})

async function submitTopup() {
  busy.value = true; err.value = ''
  try {
    await pos.topupStation(props.station.id, {
      duration_minutes: topupDuration.value,
      discount_amount: Number(topupDiscount.value) || 0,
      total_amount: Number(topupTotal.value),
    })
    showTopup.value = false
    topupDuration.value = 60; topupDiscount.value = 0; topupTotalOverride.value = null
    emit('close')
  } catch (e) { err.value = e?.response?.data?.message || 'Gagal menambah jam.' } finally { busy.value = false }
}

// --- add-on ---
const showAddon = ref(false)
const addonId = ref(null)
const addonQty = ref(1)
onMounted(async () => { try { await pos.fetchAddons() } catch (_) { /* ignore */ } })

// nominal per jam langsung muncul begitu add-on & qty dipilih (ditagih
// berjalan mengikuti waktu, sama spt sewa station — bukan sekali bayar)
const addonPreviewPerHour = computed(() => {
  const a = pos.addons.find((x) => x.id === addonId.value)
  if (!a) return 0
  return Number(a.hourly_rate || 0) * (Number(addonQty.value) || 0)
})

async function submitAddon() {
  if (!addonId.value) { err.value = 'Pilih add-on dulu.'; return }
  busy.value = true; err.value = ''
  try {
    await pos.attachAddon(props.station.id, { addon_id: addonId.value, quantity: addonQty.value })
    showAddon.value = false
    addonId.value = null; addonQty.value = 1
    emit('close')
  } catch (e) { err.value = e?.response?.data?.message || 'Gagal menambah add-on.' } finally { busy.value = false }
}

async function removeAddon(a) {
  busy.value = true
  try { await pos.detachAddon(props.station.id, a.id); emit('close') }
  catch (e) { err.value = e?.response?.data?.message || 'Gagal.' } finally { busy.value = false }
}

// --- F&B tambahan sekalian di-checkout ---
const extraCart = ref([])
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
function addExtra(p) {
  const found = extraCart.value.find((i) => i.product_id === p.id)
  if (found) found.quantity += 1
  else extraCart.value.push({ product_id: p.id, name: p.name, unit_price: p.effective_price ?? p.price, quantity: 1 })
}
function decExtra(it) {
  it.quantity -= 1
  if (it.quantity <= 0) extraCart.value = extraCart.value.filter((i) => i !== it)
}
const extraSubtotal = computed(() => extraCart.value.reduce((s, i) => s + i.unit_price * i.quantity, 0))
const grandTotal = computed(() => timeCharge.value + topupCharge.value + addonCharge.value + extraSubtotal.value)

async function doStop() {
  busy.value = true; err.value = ''
  try {
    const extraItems = extraCart.value.map((i) => ({ item_type: 'product', product_id: i.product_id, quantity: i.quantity }))
    const result = await pos.stopStation(props.station.id, extraItems)
    emit('stopped', result)
  } catch (e) { err.value = e?.response?.data?.message || 'Gagal menghentikan sesi.' } finally { busy.value = false }
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-start mb-3">
        <div>
          <h3 class="text-lg font-bold text-slate-800">{{ station.name }}</h3>
          <p class="text-xs text-slate-400">{{ session.customer_name || 'Tanpa nama' }}</p>
        </div>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <div class="text-center bg-slate-50 rounded-xl py-4 mb-3">
        <p class="text-3xl font-bold font-mono" :class="isOvertime ? 'text-red-600' : 'text-emerald-600'">{{ clockLabel }}</p>
        <p class="text-xs text-slate-400 mt-1">
          {{ rupiah(station.hourly_rate) }} / jam
          <span v-if="isCountdown">· {{ isOvertime ? 'lewat waktu' : 'sisa waktu' }} (paket {{ allocatedMinutes }} menit)</span>
        </p>
      </div>

      <div class="space-y-1 text-sm mb-3">
        <div class="flex justify-between"><span class="text-slate-500">Sewa station</span><span>{{ rupiah(timeCharge) }}</span></div>
        <div v-if="session.topups.length" class="flex justify-between"><span class="text-slate-500">Tambah waktu ({{ session.topups.length }}x)</span><span>{{ rupiah(topupCharge) }}</span></div>
        <div v-for="a in session.addons" :key="a.id" class="flex justify-between items-center">
          <span class="text-slate-500">{{ a.name }} x{{ a.quantity }}</span>
          <span class="flex items-center gap-2">
            {{ rupiah((billableMinutes / 60) * a.rate_per_hour * a.quantity) }}
            <button @click="removeAddon(a)" class="text-red-400 text-xs">✕</button>
          </span>
        </div>
        <div v-if="extraCart.length" class="flex justify-between"><span class="text-slate-500">F&amp;B tambahan</span><span>{{ rupiah(extraSubtotal) }}</span></div>
        <div class="flex justify-between font-bold text-base border-t pt-1.5 mt-1.5"><span>Total sementara</span><span class="text-brand-700">{{ rupiah(grandTotal) }}</span></div>
      </div>

      <div class="grid grid-cols-2 gap-2 mb-3">
        <button @click="showTopup = !showTopup" class="py-2 rounded-lg bg-amber-50 hover:bg-amber-100 text-amber-700 text-sm font-medium">+ Tambah Waktu</button>
        <button @click="showAddon = !showAddon" class="py-2 rounded-lg bg-purple-50 hover:bg-purple-100 text-purple-700 text-sm font-medium">+ Add-on</button>
      </div>

      <div v-if="showTopup" class="border rounded-lg p-3 mb-3 space-y-2">
        <div class="grid grid-cols-2 gap-2">
          <div><label class="block text-xs text-slate-500 mb-1">Durasi (menit)</label>
            <input v-model.number="topupDuration" type="number" class="w-full rounded border border-slate-300 px-2 py-1.5 text-sm outline-none" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Diskon</label>
            <input v-model.number="topupDiscount" type="number" class="w-full rounded border border-slate-300 px-2 py-1.5 text-sm outline-none" /></div>
        </div>
        <div><label class="block text-xs text-slate-500 mb-1">Total tagihan (otomatis — bisa diubah)</label>
          <input v-model.number="topupTotal" type="number" class="w-full rounded border border-slate-300 px-2 py-1.5 text-sm outline-none" /></div>
        <p class="text-xs text-slate-400">{{ topupDuration }} menit akan langsung ditambahkan ke sisa waktu.</p>
        <button @click="submitTopup" :disabled="busy" class="w-full py-2 rounded-lg bg-amber-600 text-white text-sm font-medium disabled:opacity-50">Simpan</button>
      </div>

      <div v-if="showAddon" class="border rounded-lg p-3 mb-3 space-y-2">
        <select v-model.number="addonId" class="w-full rounded border border-slate-300 px-2 py-1.5 text-sm outline-none">
          <option :value="null">— pilih add-on —</option>
          <option v-for="a in pos.addons" :key="a.id" :value="a.id">{{ a.name }} ({{ rupiah(a.hourly_rate) }}/jam)</option>
        </select>
        <input v-model.number="addonQty" type="number" min="1" placeholder="Qty" class="w-full rounded border border-slate-300 px-2 py-1.5 text-sm outline-none" />
        <p v-if="addonId" class="text-xs text-slate-500">≈ {{ rupiah(addonPreviewPerHour) }}/jam (ditagih mengikuti waktu berjalan)</p>
        <button @click="submitAddon" :disabled="busy" class="w-full py-2 rounded-lg bg-purple-600 text-white text-sm font-medium disabled:opacity-50">Simpan</button>
      </div>

      <div class="mb-3">
        <p class="text-xs font-semibold text-slate-400 mb-1.5">🍔 Tambah F&amp;B (opsional, sekalian checkout)</p>
        <div class="flex gap-2 mb-2">
          <input v-model="fnbSearch" placeholder="Cari menu…"
            class="flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs outline-none focus:border-brand-500" />
          <select v-if="fnbCategories.length" v-model="fnbCategory"
            class="rounded-lg border border-slate-300 px-2 py-1.5 text-xs outline-none focus:border-brand-500">
            <option value="">Semua kategori</option>
            <option v-for="c in fnbCategories" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>
        <div class="grid grid-cols-2 gap-2 max-h-40 overflow-auto">
          <button v-for="p in filteredFnb" :key="p.id" @click="addExtra(p)"
            class="text-left border rounded-lg p-2 hover:border-brand-400">
            <p class="text-xs font-medium text-slate-700 leading-tight">{{ p.name }}</p>
            <p class="text-xs text-brand-700 font-bold">{{ rupiah(p.effective_price ?? p.price) }}</p>
          </button>
          <p v-if="!filteredFnb.length" class="col-span-2 text-center text-xs text-slate-400 py-3">Menu tidak ditemukan.</p>
        </div>
        <div v-if="extraCart.length" class="mt-2 space-y-1">
          <div v-for="it in extraCart" :key="it.product_id" class="flex items-center justify-between text-xs">
            <span class="text-slate-600">{{ it.name }} x{{ it.quantity }}</span>
            <button @click="decExtra(it)" class="text-red-400">− kurangi</button>
          </div>
        </div>
      </div>

      <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">{{ err }}</p>
      <button @click="doStop" :disabled="busy"
        class="w-full py-3 rounded-lg bg-red-600 hover:bg-red-700 text-white font-semibold disabled:opacity-50">
        {{ busy ? 'Memproses…' : '⏹ STOP & Bayar' }}
      </button>
    </div>
  </div>
</template>
