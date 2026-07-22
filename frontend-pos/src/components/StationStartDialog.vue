<script setup>
import { ref, computed } from 'vue'
import { usePosStore } from '../stores/pos'

const props = defineProps({ station: Object })
const emit = defineEmits(['close', 'started'])
const pos = usePosStore()

const customerName = ref('')
// paket waktu awal — default 1 jam, langsung kepakai begitu sesi dimulai
// (supaya jam mundur aktif dr awal, tak perlu extra klik Tambah Waktu).
// Kosongkan/0 kalau mau mulai open-ended (hitung maju, tanpa paket).
const duration = ref(60)
const discount = ref(0)
const totalOverride = ref(null)
const busy = ref(false)
const err = ref('')

function rupiah(n) { return 'Rp ' + Math.round(Number(n) || 0).toLocaleString('id-ID') }

const autoTotal = computed(() => {
  const gross = (Number(duration.value) || 0) / 60 * Number(props.station.hourly_rate)
  return Math.max(0, Math.round((gross - (Number(discount.value) || 0)) * 100) / 100)
})
const total = computed({
  get: () => totalOverride.value ?? autoTotal.value,
  set: (v) => { totalOverride.value = v },
})

async function start() {
  busy.value = true
  err.value = ''
  try {
    await pos.startStation(props.station.id, customerName.value)
    if (Number(duration.value) > 0) {
      try {
        await pos.topupStation(props.station.id, {
          duration_minutes: duration.value,
          discount_amount: Number(discount.value) || 0,
          total_amount: Number(total.value),
        })
      } catch (e) {
        err.value = e?.response?.data?.message || 'Sesi dimulai, tapi gagal set paket waktu awal — tambahkan manual lewat Tambah Waktu.'
      }
    }
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

      <div class="grid grid-cols-2 gap-2 mb-2">
        <div><label class="block text-xs text-slate-500 mb-1">Paket awal (menit)</label>
          <input v-model.number="duration" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
        <div><label class="block text-xs text-slate-500 mb-1">Diskon</label>
          <input v-model.number="discount" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
      </div>
      <div class="mb-1">
        <label class="block text-xs text-slate-500 mb-1">Total tagihan (otomatis — bisa diubah)</label>
        <input v-model.number="total" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
      </div>
      <p class="text-xs text-slate-400 mb-3">
        {{ duration > 0 ? `Jam mundur mulai dari ${duration} menit.` : 'Tanpa paket — jam hitung maju (bayar sesuai waktu terpakai).' }}
      </p>

      <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">{{ err }}</p>
      <button @click="start" :disabled="busy"
        class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50">
        {{ busy ? 'Memulai…' : '▶ Mulai Sesi' }}
      </button>
    </div>
  </div>
</template>
