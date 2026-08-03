<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { usePosStore } from '../stores/pos'

const pos = usePosStore()
const emit = defineEmits(['close', 'created', 'started'])

const tab = ref('daftar') // 'daftar' | 'baru'

// ---------- daftar reservasi ----------
const date = ref(new Date().toISOString().slice(0, 10))
const rows = ref([])
const loadingList = ref(false)
async function loadList() {
  loadingList.value = true
  try { rows.value = await pos.fetchStationReservations(date.value) }
  catch (_) { rows.value = [] }
  finally { loadingList.value = false }
}

// ---------- buat reservasi ----------
const fDate = ref(new Date().toISOString().slice(0, 10))
const fStart = ref('19:00')
const fEnd = ref('21:00')
const fType = ref(null)
const fName = ref('')
const fPhone = ref('')
const types = ref([])
const busy = ref(false)
const err = ref('')

async function loadTypes() {
  try {
    types.value = await pos.fetchStationTypes({
      date: fDate.value, start_time: fStart.value, end_time: fEnd.value,
    })
    // jenis yg dipilih ternyata penuh → lepas
    const cur = types.value.find((t) => t.station_type === fType.value)
    if (cur && cur.available === 0) fType.value = null
  } catch (_) { types.value = [] }
}
watch([fDate, fStart, fEnd], loadTypes)
onMounted(async () => { await Promise.all([loadList(), loadTypes()]) })
watch(date, loadList)

const selectedType = computed(() => types.value.find((t) => t.station_type === fType.value))
const durationMinutes = computed(() => {
  const toMin = (s) => { const [h, m] = s.split(':').map(Number); return h * 60 + (m || 0) }
  let e = toMin(fEnd.value)
  if (e === 0) e = 24 * 60 // 00:00 = tengah malam (akhir hari)
  return e - toMin(fStart.value)
})
const estimasi = computed(() => {
  if (!selectedType.value || durationMinutes.value <= 0) return 0
  return Math.round((durationMinutes.value / 60) * Number(selectedType.value.rate))
})

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function fmtJam(m) {
  const h = Math.floor(m / 60), s = m % 60
  return s ? `${h} jam ${s} mnt` : `${h} jam`
}

async function submit() {
  err.value = ''
  if (!fType.value) return (err.value = 'Pilih jenis station.')
  if (durationMinutes.value <= 0) return (err.value = 'Jam selesai harus setelah jam mulai.')
  busy.value = true
  try {
    const res = await pos.createStationReservation({
      station_type: fType.value, date: fDate.value,
      start_time: fStart.value, end_time: fEnd.value,
      customer_name: fName.value || null, customer_phone: fPhone.value || null,
    })
    fName.value = ''; fPhone.value = ''
    tab.value = 'daftar'; date.value = fDate.value
    await Promise.all([loadList(), loadTypes()])
    emit('created', res) // POS buka dialog pembayaran DP
  } catch (e) {
    err.value = e?.response?.data?.message || 'Gagal membuat reservasi.'
  } finally { busy.value = false }
}

// ---------- customer datang: tentukan unit ----------
const startFor = ref(null)   // reservasi yg sedang diproses
const unitId = ref(null)
const unitErr = ref('')
const unitsOfType = computed(() => {
  const t = types.value.find((x) => x.station_type === startFor.value?.station_type)
  return t?.units || []
})
function bukaPilihUnit(r) { startFor.value = r; unitId.value = null; unitErr.value = '' }
async function mulaiSesi() {
  unitErr.value = ''
  if (!unitId.value) return (unitErr.value = 'Pilih unit dulu.')
  busy.value = true
  try {
    const res = await pos.startStationReservation(startFor.value.id, unitId.value)
    startFor.value = null
    await loadList()
    await pos.fetchStations()
    emit('started', res)
  } catch (e) {
    unitErr.value = e?.response?.data?.message || 'Gagal memulai sesi.'
  } finally { busy.value = false }
}

async function batalkan(r) {
  if (!window.confirm(`Batalkan reservasi ${r.station_type} ${r.start_time}-${r.end_time}?\nDP yang sudah dibayar HANGUS.`)) return
  try { await pos.cancelStationReservation(r.id); await loadList() }
  catch (e) { alert(e?.response?.data?.message || 'Gagal membatalkan.') }
}

const STATUS = { booked: 'Dipesan', fulfilled: 'Sedang main', cancelled: 'Batal' }
function statusClass(s) {
  return { booked: 'bg-amber-100 text-amber-700', fulfilled: 'bg-emerald-100 text-emerald-700' }[s]
    || 'bg-slate-100 text-slate-500'
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-slate-800">📅 Reservasi Station</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <div class="flex gap-1 mb-4 border-b">
        <button @click="tab = 'daftar'" :class="tab === 'daftar' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Daftar</button>
        <button @click="tab = 'baru'" :class="tab === 'baru' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Reservasi Baru</button>
      </div>

      <!-- ================= DAFTAR ================= -->
      <template v-if="tab === 'daftar'">
        <input v-model="date" type="date" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 mb-3 outline-none focus:border-brand-500" />
        <p v-if="loadingList" class="text-center text-slate-400 text-sm py-6">Memuat…</p>
        <p v-else-if="!rows.length" class="text-center text-slate-400 text-sm py-6">Tidak ada reservasi pada tanggal ini.</p>
        <div v-else class="space-y-2">
          <div v-for="r in rows" :key="r.id" class="border rounded-xl p-3">
            <div class="flex justify-between items-start gap-2">
              <div class="min-w-0">
                <p class="font-bold text-slate-800">{{ r.start_time }}–{{ r.end_time }}
                  <span class="text-sm font-normal text-slate-500">· {{ r.station_type }}</span>
                </p>
                <p class="text-sm text-slate-600 truncate">{{ r.customer_name || 'Tanpa nama' }}
                  <span v-if="r.customer_phone" class="text-slate-400">· {{ r.customer_phone }}</span>
                </p>
                <p class="text-xs text-slate-400">
                  {{ fmtJam(r.duration_minutes) }}
                  <span v-if="r.order_total"> · {{ rupiah(r.order_total) }}
                    <span v-if="r.order_due > 0" class="text-amber-600">(sisa {{ rupiah(r.order_due) }})</span>
                    <span v-else class="text-emerald-600">(lunas)</span>
                  </span>
                </p>
              </div>
              <span :class="statusClass(r.status)" class="text-xs rounded-full px-2 py-0.5 shrink-0">{{ STATUS[r.status] || r.status }}</span>
            </div>
            <div v-if="r.status === 'booked'" class="flex gap-2 mt-2">
              <button @click="bukaPilihUnit(r)" class="flex-1 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium">Customer Datang</button>
              <button @click="batalkan(r)" class="py-2 px-3 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 text-sm font-medium">Batalkan</button>
            </div>
          </div>
        </div>
      </template>

      <!-- ================= RESERVASI BARU ================= -->
      <template v-else>
        <div class="grid grid-cols-2 gap-2 mb-3">
          <div class="col-span-2">
            <label class="block text-xs text-slate-500 mb-1">Tanggal</label>
            <input v-model="fDate" type="date" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-brand-500" />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Mulai</label>
            <input v-model="fStart" type="time" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-brand-500" />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Selesai</label>
            <input v-model="fEnd" type="time" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-brand-500" />
          </div>
        </div>

        <label class="block text-xs text-slate-500 mb-1">Jenis Station</label>
        <div class="space-y-1.5 mb-3">
          <button v-for="t in types" :key="t.station_type"
            @click="t.available !== 0 && (fType = t.station_type)"
            :disabled="t.available === 0"
            :class="[
              fType === t.station_type ? 'border-brand-500 bg-brand-50' : 'border-slate-200',
              t.available === 0 ? 'opacity-50 cursor-not-allowed' : 'hover:border-brand-300',
            ]"
            class="w-full text-left border rounded-lg px-3 py-2 flex justify-between items-center">
            <span>
              <span class="font-medium text-slate-700">{{ t.station_type }}</span>
              <span class="block text-xs text-slate-400">{{ rupiah(t.rate) }}/jam</span>
            </span>
            <span class="text-xs shrink-0" :class="t.available === 0 ? 'text-red-500 font-medium' : 'text-emerald-600'">
              {{ t.available === 0 ? 'Penuh' : `${t.available}/${t.capacity} tersedia` }}
            </span>
          </button>
        </div>

        <div class="grid grid-cols-2 gap-2 mb-3">
          <div>
            <label class="block text-xs text-slate-500 mb-1">Nama Customer</label>
            <input v-model="fName" placeholder="opsional" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">No. HP</label>
            <input v-model="fPhone" placeholder="opsional" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
        </div>

        <div v-if="estimasi > 0" class="bg-slate-50 rounded-lg p-3 flex justify-between items-center mb-3">
          <span class="text-sm text-slate-500">{{ fmtJam(durationMinutes) }} × {{ rupiah(selectedType?.rate) }}</span>
          <span class="text-xl font-bold text-brand-700">{{ rupiah(estimasi) }}</span>
        </div>

        <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">{{ err }}</p>

        <button @click="submit" :disabled="busy || !fType || durationMinutes <= 0"
          class="w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-semibold disabled:opacity-40">
          {{ busy ? 'Memproses…' : 'Buat Reservasi & Bayar' }}
        </button>
        <p class="text-xs text-slate-400 mt-2 text-center">Unit ditentukan saat customer datang.</p>
      </template>
    </div>

    <!-- pilih unit saat customer datang -->
    <div v-if="startFor" class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" @click.self="startFor = null">
      <div class="bg-white w-full max-w-sm rounded-2xl p-5">
        <div class="flex justify-between items-center mb-1">
          <h3 class="text-lg font-bold text-slate-800">Pilih Unit</h3>
          <button @click="startFor = null" class="text-slate-400 text-xl">✕</button>
        </div>
        <p class="text-sm text-slate-500 mb-3">
          {{ startFor.station_type }} · {{ startFor.start_time }}–{{ startFor.end_time }} ·
          {{ fmtJam(startFor.duration_minutes) }}
        </p>
        <select v-model.number="unitId" class="w-full rounded-lg border border-slate-300 px-3 py-2.5 mb-3 outline-none focus:border-brand-500">
          <option :value="null">-- pilih unit --</option>
          <option v-for="u in unitsOfType" :key="u.id" :value="u.id">{{ u.name }}</option>
        </select>
        <p v-if="unitErr" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">{{ unitErr }}</p>
        <button @click="mulaiSesi" :disabled="busy" class="w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-semibold disabled:opacity-40">
          {{ busy ? 'Memproses…' : 'Mulai Sesi' }}
        </button>
        <p class="text-xs text-slate-400 mt-2 text-center">Jam mundur baru jalan saat tombol Play ditekan.</p>
      </div>
    </div>
  </div>
</template>
