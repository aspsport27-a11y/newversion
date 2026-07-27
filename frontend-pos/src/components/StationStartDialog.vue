<script setup>
import { ref, computed, onMounted } from 'vue'
import { usePosStore } from '../stores/pos'

const props = defineProps({ station: Object })
const emit = defineEmits(['close', 'started'])
const pos = usePosStore()

const customerName = ref('')
const hours = ref(1)
const busy = ref(false)
const err = ref('')

onMounted(async () => { if (!pos.addons.length) await pos.fetchAddons().catch(() => {}) })

function rupiah(n) { return 'Rp ' + Math.round(Number(n) || 0).toLocaleString('id-ID') }

const bookedMinutes = computed(() => Math.round((Number(hours.value) || 0) * 60))
const todayRate = computed(() => Number(props.station.today_rate ?? props.station.hourly_rate))
const sewaTotal = computed(() => (bookedMinutes.value / 60) * todayRate.value)

// --- add-on di awal (prabayar, timer sendiri) ---
const addonPick = ref(null)
const addonQty = ref(1)
const addonHours = ref(1)
const chosen = ref([]) // {addon_id, name, quantity, booked_minutes, charge}
function addAddon() {
  const a = pos.addons.find((x) => x.id === addonPick.value)
  if (!a) return
  const mins = Math.round((Number(addonHours.value) || 0) * 60)
  if (mins <= 0) return
  const charge = (mins / 60) * Number(a.hourly_rate) * (Number(addonQty.value) || 1)
  chosen.value.push({ addon_id: a.id, name: a.name, quantity: Number(addonQty.value) || 1, booked_minutes: mins, charge })
  addonPick.value = null; addonQty.value = 1; addonHours.value = 1
}
function removeAddon(i) { chosen.value.splice(i, 1) }
const addonsTotal = computed(() => chosen.value.reduce((s, a) => s + a.charge, 0))
const grandTotal = computed(() => sewaTotal.value + addonsTotal.value)

async function start() {
  err.value = ''
  if (bookedMinutes.value <= 0) { err.value = 'Isi durasi main (jam) dulu.'; return }
  busy.value = true
  try {
    const { data } = await pos.startStationFull(props.station.id, {
      customer_name: customerName.value || null,
      booked_minutes: bookedMinutes.value,
      addons: chosen.value.map((a) => ({ addon_id: a.addon_id, quantity: a.quantity, booked_minutes: a.booked_minutes })),
    })
    emit('started', data) // { session, order }
  } catch (e) {
    err.value = e?.response?.data?.message || 'Gagal memulai sesi.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-sm rounded-t-2xl sm:rounded-2xl p-5">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">Mulai Sesi — {{ station.name }}</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>
      <p class="text-sm text-slate-500 mb-3">Tarif hari ini {{ rupiah(todayRate) }} / jam</p>

      <input v-model="customerName" placeholder="Nama pelanggan / member (opsional)"
        class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500 mb-3" />

      <label class="block text-sm text-slate-600 mb-1">Main berapa jam?</label>
      <div class="flex gap-2 mb-2">
        <button v-for="h in [1, 2, 3]" :key="h" @click="hours = h"
          :class="Number(hours) === h ? 'bg-brand-600 text-white border-brand-600' : 'bg-white text-slate-600 border-slate-300'"
          class="flex-1 py-2 rounded-lg border text-sm font-medium">{{ h }} jam</button>
      </div>
      <input v-model.number="hours" type="number" min="0.5" step="0.5" inputmode="decimal"
        class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-right outline-none focus:border-brand-500 mb-3" />

      <!-- Add-on (opsional) — prabayar, timer sendiri -->
      <div v-if="pos.addons.length" class="border rounded-lg p-3 mb-3">
        <p class="text-xs font-semibold text-purple-700 mb-2">🎮 Add-on (opsional)</p>
        <div v-for="(a, i) in chosen" :key="i" class="flex justify-between items-center text-sm mb-1">
          <span class="text-slate-600">{{ a.name }} x{{ a.quantity }} · {{ a.booked_minutes }}mnt</span>
          <span class="flex items-center gap-2">{{ rupiah(a.charge) }}
            <button @click="removeAddon(i)" class="text-red-400 text-xs">✕</button></span>
        </div>
        <div class="grid grid-cols-3 gap-1.5 mt-1">
          <select v-model.number="addonPick" class="col-span-3 rounded border border-slate-300 px-2 py-1.5 text-sm outline-none">
            <option :value="null">— pilih add-on —</option>
            <option v-for="a in pos.addons" :key="a.id" :value="a.id">{{ a.name }} ({{ rupiah(a.hourly_rate) }}/jam)</option>
          </select>
          <input v-model.number="addonQty" type="number" min="1" placeholder="Qty" class="rounded border border-slate-300 px-2 py-1.5 text-sm outline-none" />
          <input v-model.number="addonHours" type="number" min="0.5" step="0.5" placeholder="Jam" class="rounded border border-slate-300 px-2 py-1.5 text-sm outline-none" />
          <button @click="addAddon" :disabled="!addonPick" class="rounded bg-purple-100 text-purple-700 text-sm font-medium disabled:opacity-40">+ Tambah</button>
        </div>
      </div>

      <div class="bg-slate-50 rounded-lg px-3 py-2.5 mb-3 text-sm space-y-1">
        <div class="flex justify-between"><span class="text-slate-500">Sewa station ({{ bookedMinutes }} menit)</span><span>{{ rupiah(sewaTotal) }}</span></div>
        <div v-if="addonsTotal > 0" class="flex justify-between"><span class="text-slate-500">Add-on</span><span>{{ rupiah(addonsTotal) }}</span></div>
        <div class="flex justify-between font-bold border-t pt-1"><span>Total bayar di depan</span><span class="text-brand-700">{{ rupiah(grandTotal) }}</span></div>
      </div>

      <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">{{ err }}</p>
      <button @click="start" :disabled="busy || bookedMinutes <= 0"
        class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50">
        {{ busy ? 'Memulai…' : '▶ Bayar & Mulai Sesi' }}
      </button>
    </div>
  </div>
</template>
