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

// Kompres foto bukti di HP → JPEG maks ~1600px & di bawah 3MB, supaya foto
// besar dari kamera tetap bisa dipakai (tak lagi ditolak "maks 3MB").
function compressImageToDataUrl(file, maxDim = 1600, maxBytes = 2_800_000) {
  return new Promise((resolve, reject) => {
    if (!file.type?.startsWith('image/')) {
      // bukan gambar (mis. PDF) → pakai apa adanya kalau muat, else tolak
      if (file.size > maxBytes) { reject(new Error('File > 3MB & bukan gambar (tak bisa dikompres).')); return }
      const r = new FileReader(); r.onload = () => resolve(r.result); r.onerror = reject; r.readAsDataURL(file); return
    }
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => {
      URL.revokeObjectURL(url)
      let { width, height } = img
      const scale = Math.min(1, maxDim / Math.max(width, height))
      width = Math.round(width * scale); height = Math.round(height * scale)
      const canvas = document.createElement('canvas')
      canvas.width = width; canvas.height = height
      canvas.getContext('2d').drawImage(img, 0, 0, width, height)
      let q = 0.8, out = canvas.toDataURL('image/jpeg', q)
      // turunkan kualitas bertahap sampai muat
      while (out.length * 0.75 > maxBytes && q > 0.4) { q -= 0.1; out = canvas.toDataURL('image/jpeg', q) }
      resolve(out)
    }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Gagal membaca gambar.')) }
    img.src = url
  })
}

async function onProofChange(e) {
  proofErr.value = ''
  const file = e.target.files[0]
  if (!file) return
  try {
    proofPreview.value = await compressImageToDataUrl(file)
  } catch (err) {
    proofErr.value = err?.message || 'Gagal memproses foto.'
    e.target.value = ''
  }
}

const sisa = computed(() => Math.max(0, props.total - (Number(amount.value) || 0)))
const change = computed(() => Math.max(0, (Number(received.value) || 0) - (Number(amount.value) || 0)))
// bayar 0 = booking tanpa DP → order dibuat 'open' & masuk menu Pelunasan (tak ada
// pembayaran/metode yg diproses sekarang)
const noPay = computed(() => (Number(amount.value) || 0) === 0)
const validAmount = computed(() => {
  const a = Number(amount.value) || 0
  return a >= 0 && a <= props.total
})
const canPayCash = computed(() => noPay.value || (validAmount.value && (Number(received.value) || 0) >= (Number(amount.value) || 0)))
// QRIS manual (bukan dinamis) butuh bukti sama seperti transfer
const qrisManual = computed(() => !props.qrisDynamic)
const canPayQrisDynamic = computed(() => noPay.value || validAmount.value)
const canPayQrisManual = computed(() => noPay.value || (validAmount.value && !!proofPreview.value))
const canPayTransfer = computed(() => noPay.value || (validAmount.value && !!proofPreview.value))
const payLabel = computed(() => noPay.value ? 'Simpan Booking (Tanpa DP)' : (sisa.value > 0 ? 'Bayar DP & Cetak' : 'Bayar & Cetak Struk'))

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function setDp() { amount.value = Math.round(props.total / 2) }
function setFull() { amount.value = props.total }
function setNoDp() { amount.value = 0 }
function quickReceived(v) { received.value = String(v) }

// --- Split bill: bayar 1 tagihan pakai beberapa metode ---
const splitMode = ref(false)
const splits = ref([
  { method: 'cash', amount: null, proof: '', reference: '' },
  { method: 'qris', amount: null, proof: '', reference: '' },
])
function splitNeedsProof(m) { return m === 'transfer' || (m === 'qris' && qrisManual.value) }
function addSplit() { splits.value.push({ method: 'cash', amount: null, proof: '', reference: '' }) }
function rmSplit(i) { if (splits.value.length > 2) splits.value.splice(i, 1) }
async function onSplitProof(i, e) {
  proofErr.value = ''
  const file = e.target.files[0]; if (!file) return
  try {
    splits.value[i].proof = await compressImageToDataUrl(file)
  } catch (err) {
    proofErr.value = err?.message || 'Gagal memproses foto.'
    e.target.value = ''
  }
}
const splitSum = computed(() => splits.value.reduce((t, s) => t + (Number(s.amount) || 0), 0))
const splitRemaining = computed(() => (Number(amount.value) || 0) - splitSum.value)
const splitValid = computed(() =>
  Math.abs(splitRemaining.value) < 0.5 &&
  splits.value.every((s) => (Number(s.amount) || 0) > 0 && (!splitNeedsProof(s.method) || !!s.proof)),
)
// autofill baris terakhir dgn sisa (mempercepat)
function fillRemaining(i) {
  const others = splits.value.reduce((t, s, idx) => t + (idx === i ? 0 : (Number(s.amount) || 0)), 0)
  splits.value[i].amount = Math.max(0, (Number(amount.value) || 0) - others)
}

async function confirm() {
  submitting.value = true
  try {
    if (splitMode.value) {
      await emit('pay', {
        amount: Number(amount.value),
        splits: splits.value.map((s) => ({
          method: s.method, amount: Number(s.amount),
          reference: s.method !== 'cash' ? (s.reference || null) : null,
          proof_image: splitNeedsProof(s.method) ? s.proof : null,
        })),
      })
      return
    }
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
            <button @click="setNoDp" class="text-xs bg-slate-100 text-slate-600 rounded px-2 py-1">Tanpa DP</button>
            <button @click="setDp" class="text-xs bg-amber-100 text-amber-700 rounded px-2 py-1">DP 50%</button>
            <button @click="setFull" class="text-xs bg-slate-100 text-slate-600 rounded px-2 py-1">Penuh</button>
          </div>
        </div>
        <input v-model.number="amount" type="number" inputmode="numeric"
          class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-lg text-right outline-none focus:border-brand-500" />
        <p v-if="noPay" class="text-sm text-slate-500 mt-1 text-right">Tanpa DP — masuk menu Pelunasan (bayar penuh nanti)</p>
        <p v-else-if="sisa > 0" class="text-sm text-amber-600 mt-1 text-right">Sisa (DP): {{ rupiah(sisa) }}</p>
      </div>

      <!-- Tanpa DP: langsung simpan booking, tanpa metode bayar -->
      <button v-if="noPay" @click="confirm" :disabled="submitting"
        class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50">
        {{ submitting ? 'Memproses…' : 'Simpan Booking (Tanpa DP)' }}
      </button>

      <template v-if="!noPay">
      <!-- Toggle: 1 metode vs split -->
      <div class="flex gap-2 mb-3">
        <button @click="splitMode = false" :class="!splitMode ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-500'" class="flex-1 py-2 rounded-lg text-sm font-medium">1 Metode</button>
        <button @click="splitMode = true" :class="splitMode ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-500'" class="flex-1 py-2 rounded-lg text-sm font-medium">🔀 Split (Cash + QRIS/Transfer)</button>
      </div>

      <!-- ===== SPLIT BILL ===== -->
      <div v-if="splitMode" class="space-y-2">
        <div v-for="(s, i) in splits" :key="i" class="border border-slate-200 rounded-lg p-2 space-y-1.5">
          <div class="flex gap-2 items-center">
            <select v-model="s.method" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm w-28 outline-none">
              <option value="cash">💵 Cash</option>
              <option value="qris">📱 QRIS</option>
              <option value="transfer">🏦 Transfer</option>
            </select>
            <input v-model.number="s.amount" type="number" inputmode="numeric" placeholder="Jumlah"
              class="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm text-right outline-none focus:border-brand-500" />
            <button type="button" @click="fillRemaining(i)" title="Isi sisa" class="text-xs text-brand-600 px-1 whitespace-nowrap">sisa</button>
            <button v-if="splits.length > 2" @click="rmSplit(i)" class="text-red-400 px-1">✕</button>
          </div>
          <label v-if="splitNeedsProof(s.method)" class="flex items-center gap-2 text-xs cursor-pointer">
            <input type="file" accept="image/*" class="hidden" @change="onSplitProof(i, $event)" />
            <span class="inline-block rounded-lg border border-dashed border-slate-300 px-2 py-1 text-slate-500">{{ s.proof ? '✅ bukti terpilih' : '📎 upload bukti (' + s.method + ')' }}</span>
          </label>
        </div>
        <button @click="addSplit" class="text-brand-600 text-sm">+ metode</button>
        <div class="flex justify-between text-sm border-t pt-2">
          <span class="text-slate-500">Terbagi</span>
          <span class="font-semibold" :class="Math.abs(splitRemaining) < 0.5 ? 'text-emerald-600' : 'text-amber-600'">{{ rupiah(splitSum) }} / {{ rupiah(amount) }}</span>
        </div>
        <p v-if="splitRemaining > 0" class="text-xs text-amber-600 text-right">Kurang {{ rupiah(splitRemaining) }}</p>
        <p v-else-if="splitRemaining < 0" class="text-xs text-red-600 text-right">Lebih {{ rupiah(-splitRemaining) }}</p>
        <p v-if="proofErr" class="text-xs text-red-600">{{ proofErr }}</p>
        <button @click="confirm" :disabled="!splitValid || submitting"
          class="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50">
          {{ submitting ? 'Memproses…' : (sisa > 0 ? 'Bayar DP (Split) & Cetak' : 'Bayar (Split) & Cetak Struk') }}
        </button>
      </div>

      <template v-else>
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
        <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onProofChange" />
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
        <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onProofChange" />
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
      </template>
      </template>
    </div>
  </div>
</template>
