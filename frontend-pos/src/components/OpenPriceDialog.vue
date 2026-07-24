<script setup>
import { ref } from 'vue'

const props = defineProps({ name: { type: String, default: 'Item' } })
const emit = defineEmits(['add', 'close'])

const amount = ref('')
const PRESETS = [2000, 5000, 10000]

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function preset(v) { amount.value = String(v) }
function submit() {
  const v = Number(amount.value) || 0
  if (v <= 0) return
  emit('add', v)
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-sm rounded-t-2xl sm:rounded-2xl p-5">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">{{ name }}</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <label class="block text-sm text-slate-600 mb-1">Nominal</label>
      <input v-model="amount" type="number" inputmode="numeric" placeholder="0" autofocus
        @keyup.enter="submit"
        class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-2xl text-right font-bold outline-none focus:border-brand-500 mb-3" />

      <div class="grid grid-cols-3 gap-2 mb-4">
        <button v-for="v in PRESETS" :key="v" @click="preset(v)"
          class="py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium">
          {{ rupiah(v) }}
        </button>
      </div>

      <button @click="submit" :disabled="!(Number(amount) > 0)"
        class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50">
        Tambah ke Keranjang
      </button>
    </div>
  </div>
</template>
