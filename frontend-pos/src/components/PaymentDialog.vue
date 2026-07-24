<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  total: Number,
  allowDp: { type: Boolean, default: true },
  title: { type: String, default: 'Pembayaran' },
  // true = QR otomatis via BRIAPI; false = QRIS manual (customer scan kartu statis, upload bukti)
  qrisDynamic: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'pay'])

const method = ref('cash')
const amount = ref(props.total) // jumlah dibayar sekarang
const received = ref('') // uang tunai diterima (untuk kembalian)
const reference = ref('')
const submitting = ref(false)

// bukti transfer bank — foto/screenshot, wajib sblm konfirmasi
const fileInput = ref(null)
const proofPreview = ref('') // base64 data URL
const proofErr = ref('')
function pickProof() { fileInput.value?.click() }
function onProofChange(e) {
  proofErr.value = ''
  const file = e.target.files[0]
  if (!file) return
  if (file.size > 3_000_000) { proofErr.value = 'Ukuran file maks 3MB.'; e.target.value = ''; return }
  const reader = new FileReader()
  reader.onload = () => { proofPreview.value = reader.result }
  reader.readAsDataURL(file)
}

const sisa = computed(() => Math.max(0, props.total - (Number(amount.value) || 0)))
const change = computed(() => Math.max(0, (Number(received.value) || 0) - (Number(amount.value) || 0)))
const validAmount = computed(() => {
  const a = Number(amount.value) || 0
  return a > 0 && a <= props.total
})
const canPayCash = computed(() => validAmount.value && (Number(received.value) || 0) >= (Number(amount.value) || 0))
// QRIS manual (bukan dinamis) butuh bukti sama seperti transfer
const qrisManual = computed(() => !props.qrisDynamic)
const canPayQrisManual = computed(() => validAmount.value && !!proofPreview.value)

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function setDp() { amount.value = Math.round(props.total / 2) }
function setFull() { amount.value = props.total }
function quickReceived(v) { received.value = String(v) }

async function confirm() {
  submitting.value = true
  try {
    const needProof = method.value === 'transfer' || (method.value === 'qris' && qrisManual.value)
    await emit('pay', {
      method: method.value,
      amount: Number(amount.value),
      reference: method.value !== 'cash' ? reference.value : null,
      proof_image: needProof ? proofPreview.value : null,
    })
  } finally { submitting.value = false }
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">{{ title }}</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <div class="text-center mb-4">
        <p class="text-sm text-slate-500">Total tagihan</p>
        <p class="text-3xl font-bold text-brand-700">{{ rupiah(total) }}</p>
      </div>

      <!-- Jumlah dibayar (DP / penuh) -->
      <div v-if="allowDp" class="mb-4">
        <div class="flex justify-between items-center mb-1">
          <label class="text-sm text-slate-600">Jumlah dibayar sekarang</label>
          <div class="flex gap-1">
            <button @click="setDp" class="text-xs bg-amber-100 text-amber-700 rounded px-2 py-1">DP 50%</button>
            <button @click="setFull" class="text-xs bg-slate-100 text-slate-600 rounded px-2 py-1">Penuh</button>
          </div>
        </div>
        <input v-model.number="amount" type="number" inputmode="numeric"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-lg text-right outline-none focus:border-brand-500" />
        <p v-if="sisa > 0" class="text-sm text-amber-600 mt-1 text-right">Sisa (DP): {{ rupiah(sisa) }}</p>
      </div>

      <div class="grid grid-cols-3 gap-2 mb-4">
        <button @click="method = 'cash'" :class="method === 'cash' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600'" class="py-2.5 rounded-lg font-medium text-sm">💵 Cash</button>
        <button @click="method = 'qris'" :class="method === 'qris' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600'" class="py-2.5 rounded-lg font-medium text-sm">📱 QRIS</button>
        <button @click="method = 'transfer'" :class="method === 'transfer' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600'" class="py-2.5 rounded-lg font-medium text-sm">🏦 Transfer</button>
      </div>

      <!-- CASH -->
      <div v-if="method === 'cash'" class="space-y-3">
        <input v-model="received" type="number" inputmode="numeric" placeholder="Uang diterima"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-lg text-right outline-none focus:border-brand-500" />
        <div class="grid grid-cols-4 gap-2">
          <button v-for="v in [amount, 50000, 100000, 200000]" :key="v" @click="quickReceived(v)"
            class="py-1.5 text-xs rounded bg-slate-100 hover:bg-slate-200 text-slate-600">
            {{ v === amount ? 'Pas' : (v / 1000) + 'rb' }}
          </button>
        </div>
        <div class="flex justify-between text-sm">
          <span class="text-slate-500">Kembalian</span>
          <span class="font-semibold text-slate-800">{{ rupiah(change) }}</span>
        </div>
        <button @click="confirm" :disabled="!canPayCash || submitting"
          class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50">
          {{ submitting ? 'Memproses…' : (sisa > 0 ? 'Bayar DP & Cetak' : 'Bayar & Cetak Struk') }}
        </button>
      </div>

      <!-- QRIS DINAMIS (BRIAPI aktif) -->
      <div v-else-if="method === 'qris' && !qrisManual" class="space-y-3">
        <div class="bg-brand-50 border border-brand-100 rounded-lg p-3 text-sm text-brand-800">
          QR akan ditampilkan untuk dipindai customer. Transaksi otomatis lunas
          begitu bank mengonfirmasi — <span class="font-medium">jangan tutup layar QR</span>
          sebelum pembayaran masuk.
        </div>
        <input v-model="reference" placeholder="No. referensi (opsional)"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500" />
        <button @click="confirm" :disabled="!validAmount || submitting"
          class="w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-semibold disabled:opacity-50">
          {{ submitting ? 'Membuat QR…' : 'Tampilkan QR' }}
        </button>
      </div>

      <!-- QRIS MANUAL (kartu statis — wajib upload bukti, spt transfer) -->
      <div v-else-if="method === 'qris' && qrisManual" class="space-y-3">
        <div class="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
          Customer scan QRIS (kartu). <span class="font-medium">Pastikan dana masuk</span>
          (cek BRImo/notifikasi), lalu foto/upload bukti sebelum konfirmasi.
        </div>
        <input ref="fileInput" type="file" accept="image/*" capture="environment" class="hidden" @change="onProofChange" />
        <button @click="pickProof" type="button"
          class="w-full py-3 rounded-lg border-2 border-dashed border-slate-300 hover:border-brand-400 text-sm text-slate-500">
          {{ proofPreview ? '✅ Bukti terpilih — ganti foto?' : '📎 Pilih / Foto Bukti QRIS' }}
        </button>
        <img v-if="proofPreview" :src="proofPreview" class="w-full max-h-48 object-contain rounded-lg border border-slate-200" />
        <input v-model="reference" placeholder="No. referensi / catatan (opsional)"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500" />
        <p v-if="proofErr" class="text-xs text-red-600">{{ proofErr }}</p>
        <button @click="confirm" :disabled="!canPayQrisManual || submitting"
          class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50">
          {{ submitting ? 'Memproses…' : (sisa > 0 ? 'Bayar DP & Cetak' : 'Bayar & Cetak Struk') }}
        </button>
      </div>

      <!-- TRANSFER BANK -->
      <div v-else class="space-y-3">
        <div class="bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm text-slate-600">
          Cek dulu bukti transfer dari customer, lalu upload sebelum konfirmasi.
        </div>
        <input ref="fileInput" type="file" accept="image/*" capture="environment" class="hidden" @change="onProofChange" />
        <button @click="pickProof" type="button"
          class="w-full py-3 rounded-lg border-2 border-dashed border-slate-300 hover:border-brand-400 text-sm text-slate-500">
          {{ proofPreview ? '✅ Bukti terpilih — ganti foto?' : '📎 Pilih / Foto Bukti Transfer' }}
        </button>
        <img v-if="proofPreview" :src="proofPreview" class="w-full max-h-48 object-contain rounded-lg border border-slate-200" />
        <input v-model="reference" placeholder="No. referensi / catatan (opsional)"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500" />
        <p v-if="proofErr" class="text-xs text-red-600">{{ proofErr }}</p>
        <button @click="confirm" :disabled="!validAmount || !proofPreview || submitting"
          class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50">
          {{ submitting ? 'Memproses…' : (sisa > 0 ? 'Bayar DP & Cetak' : 'Bayar & Cetak Struk') }}
        </button>
      </div>
    </div>
  </div>
</template>
