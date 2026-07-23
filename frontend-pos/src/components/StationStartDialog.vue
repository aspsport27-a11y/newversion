<script setup>
import { ref, computed } from 'vue'
import { usePosStore } from '../stores/pos'

const props = defineProps({ station: Object })
const emit = defineEmits(['close', 'started'])
const pos = usePosStore()

const customerName = ref('')
// durasi main = PAKET TETAP yg dipesan customer di awal (jam). Sewa station
// langsung fix = jam x tarif/jam (bukan dihitung per menit terpakai). Jam di
// layar sesi jadi hitung mundur dari durasi ini.
const hours = ref(1)
const busy = ref(false)
const err = ref('')

function rupiah(n) { return 'Rp ' + Math.round(Number(n) || 0).toLocaleString('id-ID') }

const bookedMinutes = computed(() => Math.round((Number(hours.value) || 0) * 60))
const sewaTotal = computed(() => (bookedMinutes.value / 60) * Number(props.station.hourly_rate))

async function start() {
  err.value = ''
  if (bookedMinutes.value <= 0) { err.value = 'Isi durasi main (jam) dulu.'; return }
  busy.value = true
  try {
    await pos.startStation(props.station.id, customerName.value, bookedMinutes.value)
    emit('started')
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
      <p class="text-sm text-slate-500 mb-3">Tarif {{ rupiah(station.hourly_rate) }} / jam</p>

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

      <div class="flex justify-between items-center bg-slate-50 rounded-lg px-3 py-2.5 mb-3">
        <span class="text-sm text-slate-500">Sewa station ({{ bookedMinutes }} menit)</span>
        <span class="text-lg font-bold text-brand-700">{{ rupiah(sewaTotal) }}</span>
      </div>

      <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">{{ err }}</p>
      <button @click="start" :disabled="busy || bookedMinutes <= 0"
        class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50">
        {{ busy ? 'Memulai…' : '▶ Mulai Sesi' }}
      </button>
    </div>
  </div>
</template>
