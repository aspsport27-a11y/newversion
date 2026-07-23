<script setup>
import { ref } from 'vue'
import { usePosStore } from '../stores/pos'

const props = defineProps({ station: Object })
const emit = defineEmits(['close', 'started'])
const pos = usePosStore()

const customerName = ref('')
const busy = ref(false)
const err = ref('')

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }

async function start() {
  busy.value = true
  err.value = ''
  try {
    // Mulai sesi TIDAK bikin entry "Tambah Waktu" — itu cuma dipakai lewat
    // tombol Tambah Waktu saat sesi berjalan. "Sewa station" (elapsed x
    // tarif/jam) sudah otomatis jalan sejak sesi dimulai; kalau start jg
    // bikin topup, customer kena tagih dua kali utk periode yg sama.
    await pos.startStation(props.station.id, customerName.value)
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

      <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">{{ err }}</p>
      <button @click="start" :disabled="busy"
        class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50">
        {{ busy ? 'Memulai…' : '▶ Mulai Sesi' }}
      </button>
    </div>
  </div>
</template>
