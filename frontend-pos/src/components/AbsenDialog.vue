<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import client from '../api/client'

const props = defineProps({ terminalCode: { type: String, default: '' } })
const emit = defineEmits(['close'])

const terminal = ref(props.terminalCode || localStorage.getItem('pos_terminal_code') || '')
const pin = ref('')
const busy = ref(false)
const err = ref('')
const ok = ref('')

// ---- kamera ----
const videoEl = ref(null)
const camOk = ref(false)
let stream = null
async function startCam() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 320 } })
    if (videoEl.value) videoEl.value.srcObject = stream
    camOk.value = true
  } catch (e) { camOk.value = false }
}
function stopCam() { if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null } }
function capture() {
  if (!camOk.value || !videoEl.value) return null
  const v = videoEl.value
  const w = 320
  const h = v.videoWidth ? Math.round((v.videoHeight / v.videoWidth) * w) : 240
  const c = document.createElement('canvas')
  c.width = w; c.height = h
  c.getContext('2d').drawImage(v, 0, 0, w, h)
  return c.toDataURL('image/jpeg', 0.6)
}

function tap(d) { if (pin.value.length < 8) pin.value += d }
function backspace() { pin.value = pin.value.slice(0, -1) }

async function absen(action) {
  if (!terminal.value || !pin.value) { err.value = 'Isi Terminal & PIN dulu.'; ok.value = ''; return }
  err.value = ''; ok.value = ''; busy.value = true
  const photo = capture()
  try {
    const { data } = await client.post('/attendance', {
      terminal_code: terminal.value.trim(), pin: pin.value, action, photo,
    })
    ok.value = data.message
    localStorage.setItem('pos_terminal_code', terminal.value.trim())
    pin.value = ''
  } catch (e) {
    err.value = e?.response?.data?.message || 'Absen gagal.'
    pin.value = ''
  } finally { busy.value = false }
}
function close() { stopCam(); emit('close') }

onMounted(startCam)
onBeforeUnmount(stopCam)
</script>

<template>
  <div class="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" @click.self="close">
    <div class="bg-white w-full max-w-xs rounded-2xl p-5">
      <div class="flex justify-between items-center mb-3">
        <h3 class="text-lg font-bold text-slate-800">🕐 Absen</h3>
        <button @click="close" class="text-slate-400 text-xl">✕</button>
      </div>

      <!-- kamera -->
      <div class="rounded-xl overflow-hidden bg-slate-900 mb-3 aspect-[4/3] grid place-items-center">
        <video v-show="camOk" ref="videoEl" autoplay playsinline muted class="w-full h-full object-cover"></video>
        <p v-if="!camOk" class="text-slate-400 text-xs text-center px-3">Kamera tidak tersedia — absen tetap tercatat tanpa foto.</p>
      </div>

      <input v-model="terminal" placeholder="Kode Terminal"
        class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm mb-2 outline-none focus:border-brand-500" />

      <div class="flex justify-center gap-2 py-1 mb-1">
        <span v-for="n in 4" :key="n" class="h-3 w-3 rounded-full" :class="pin.length >= n ? 'bg-brand-600' : 'bg-slate-200'" />
      </div>

      <div class="grid grid-cols-3 gap-1.5 mb-3">
        <button v-for="d in ['1','2','3','4','5','6','7','8','9']" :key="d" @click="tap(d)"
          class="py-2.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-lg font-semibold text-slate-700 active:scale-95">{{ d }}</button>
        <button @click="backspace" class="py-2.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-500 active:scale-95">⌫</button>
        <button @click="tap('0')" class="py-2.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-lg font-semibold text-slate-700 active:scale-95">0</button>
        <div></div>
      </div>

      <div class="grid grid-cols-2 gap-2">
        <button @click="absen('in')" :disabled="busy" class="py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold active:scale-95 disabled:opacity-60">🕐 Masuk</button>
        <button @click="absen('out')" :disabled="busy" class="py-2.5 rounded-lg bg-slate-600 hover:bg-slate-700 text-white text-sm font-semibold active:scale-95 disabled:opacity-60">🏠 Pulang</button>
      </div>

      <p v-if="err" class="text-sm text-center text-red-600 bg-red-50 rounded-lg px-3 py-2 mt-3">{{ err }}</p>
      <p v-if="ok" class="text-sm text-center text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2 mt-3 font-medium">{{ ok }}</p>
    </div>
  </div>
</template>
