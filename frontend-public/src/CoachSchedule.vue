<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const props = defineProps({ token: String })
const api = axios.create({ baseURL: '/api/public' })

const loading = ref(true)
const invalid = ref(false)
const coach = ref(null)
const venue = ref(null)
const sessions = ref([])

// ---------- Atur Ketersediaan ----------
const HARI = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu'] // 0..6 = date.weekday() Python
const tab = ref('jadwal') // 'jadwal' | 'atur'
// pola[wd] = array rentang {start_time, end_time}
const pola = ref(HARI.map(() => []))
const exceptions = ref([])
const conflicts = ref([])
const savingPola = ref(false)
const savedMsg = ref('')
const excForm = ref({ date: '', available: false, start_time: '18:00', end_time: '22:00' })
const excBusy = ref(false)
const excErr = ref('')
const belumDiatur = computed(() => pola.value.every((d) => !d.length))

async function loadAvailability() {
  const { data } = await api.get('/coach-availability', { params: { token: props.token } })
  const p = HARI.map(() => [])
  for (const r of data.pattern) p[r.weekday].push({ start_time: r.start_time, end_time: r.end_time })
  pola.value = p
  exceptions.value = data.exceptions
  conflicts.value = data.conflicts
}
function tambahRentang(wd) {
  pola.value[wd].push({ start_time: '18:00', end_time: '22:00' })
}
function hapusRentang(wd, i) {
  pola.value[wd].splice(i, 1)
}
async function simpanPola() {
  savingPola.value = true
  savedMsg.value = ''
  try {
    const pattern = []
    pola.value.forEach((ranges, wd) =>
      ranges.forEach((r) => pattern.push({ weekday: wd, start_time: r.start_time, end_time: r.end_time })),
    )
    const { data } = await api.put('/coach-availability', { pattern }, { params: { token: props.token } })
    conflicts.value = data.conflicts
    savedMsg.value = 'Ketersediaan tersimpan ✓'
    setTimeout(() => (savedMsg.value = ''), 3000)
  } catch (e) {
    savedMsg.value = e?.response?.data?.message || 'Gagal menyimpan.'
  } finally {
    savingPola.value = false
  }
}
async function tambahPengecualian() {
  excErr.value = ''
  if (!excForm.value.date) { excErr.value = 'Pilih tanggal dulu.'; return }
  excBusy.value = true
  try {
    const { data } = await api.post('/coach-availability/exception', { ...excForm.value }, { params: { token: props.token } })
    exceptions.value = data.exceptions
    conflicts.value = data.conflicts
    excForm.value.date = ''
  } catch (e) {
    excErr.value = e?.response?.data?.message || 'Gagal menyimpan.'
  } finally { excBusy.value = false }
}
async function hapusPengecualian(e) {
  try {
    await api.delete(`/coach-availability/exception/${e.id}`, { params: { token: props.token } })
    exceptions.value = exceptions.value.filter((x) => x.id !== e.id)
  } catch (_) { /* biarkan */ }
}

onMounted(async () => {
  // halaman ini berisi data pribadi customer — jangan sampai terindeks mesin
  // pencari (URL-nya rahasia, ini lapisan pengaman tambahan)
  const m = document.createElement('meta')
  m.name = 'robots'
  m.content = 'noindex, nofollow'
  document.head.appendChild(m)
  try {
    const { data } = await api.get('/coach-schedule', { params: { token: props.token } })
    coach.value = data.coach
    venue.value = data.venue
    sessions.value = data.sessions
    document.title = `Jadwal ${data.coach.name} — ASP Sports`
    await loadAvailability()
  } catch (_) {
    invalid.value = true
  } finally {
    loading.value = false
  }
})

// kelompokkan per tanggal supaya enak dibaca
const byDate = computed(() => {
  const map = new Map()
  for (const s of sessions.value) {
    if (!map.has(s.date)) map.set(s.date, [])
    map.get(s.date).push(s)
  }
  return [...map.entries()].map(([date, items]) => ({ date, items }))
})

const totalHours = computed(() =>
  sessions.value.reduce((t, s) => t + (Number(s.hours) || 0), 0),
)

function fmtDate(iso) {
  const d = new Date(iso + 'T00:00:00')
  const hari = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu'][d.getDay()]
  const bulan = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'][d.getMonth()]
  return `${hari}, ${d.getDate()} ${bulan} ${d.getFullYear()}`
}
function isToday(iso) {
  return iso === new Date().toISOString().slice(0, 10)
}
function waLink(phone) {
  if (!phone) return null
  let digits = String(phone).replace(/\D/g, '')
  if (!digits) return null
  if (digits.startsWith('0')) digits = '62' + digits.slice(1)
  else if (!digits.startsWith('62')) digits = '62' + digits
  return `https://wa.me/${digits}`
}
function fmtJam(n) {
  const h = Number(n) || 0
  return Number.isInteger(h) ? `${h} jam` : `${h.toFixed(1)} jam`
}
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <header class="bg-white border-b">
      <div class="max-w-2xl mx-auto px-4 py-4 flex items-center gap-3">
        <img src="/asp-logo.png" alt="ASP Sports" class="h-9" />
        <div>
          <h1 class="font-bold text-slate-800 leading-tight">Jadwal Coaching</h1>
          <p v-if="coach" class="text-sm text-slate-500">{{ coach.name }}<span v-if="venue?.name"> · {{ venue.name }}</span></p>
        </div>
      </div>
    </header>

    <main class="max-w-2xl mx-auto px-4 py-5">
      <p v-if="loading" class="text-slate-400 text-sm">Memuat jadwal…</p>

      <div v-else-if="invalid" class="bg-white rounded-xl border p-6 text-center">
        <p class="text-3xl mb-2">🔒</p>
        <p class="font-medium text-slate-700">Tautan tidak berlaku</p>
        <p class="text-sm text-slate-500 mt-1">Tautan mungkin sudah diganti. Silakan minta tautan baru ke pengelola venue.</p>
      </div>

      <template v-else>
        <!-- Tab -->
        <div class="flex gap-1 mb-4 border-b">
          <button @click="tab = 'jadwal'" :class="tab === 'jadwal' ? 'border-teal-600 text-teal-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Jadwal Saya</button>
          <button @click="tab = 'atur'" :class="tab === 'atur' ? 'border-teal-600 text-teal-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Atur Ketersediaan</button>
        </div>

        <!-- ============ ATUR KETERSEDIAAN ============ -->
        <div v-if="tab === 'atur'">
          <p class="text-sm text-slate-500 mb-4">
            Beri tahu venue kapan Anda bisa melatih. Petugas akan melihat ini saat membuatkan booking.
          </p>

          <div v-if="conflicts.length" class="bg-amber-50 border border-amber-300 rounded-lg p-3 mb-4">
            <p class="text-sm font-medium text-amber-800 mb-1">⚠️ Ada {{ conflicts.length }} sesi yang sudah terjadwal di luar ketersediaan Anda</p>
            <p v-for="(c, i) in conflicts" :key="i" class="text-xs text-amber-700">
              {{ fmtDate(c.date) }} · {{ c.start_time }}–{{ c.end_time }} · {{ c.facility_name }}
            </p>
            <p class="text-xs text-amber-700 mt-1.5">Sesi ini <b>tidak dibatalkan</b> — silakan hubungi venue untuk menyelesaikannya.</p>
          </div>

          <p v-if="belumDiatur" class="bg-slate-100 rounded-lg p-3 text-xs text-slate-600 mb-4">
            Belum diatur — selama kosong, Anda dianggap <b>selalu bisa</b>. Isi jadwal di bawah supaya petugas tahu kapan Anda benar-benar tersedia.
          </p>

          <!-- Pola mingguan -->
          <div class="bg-white rounded-xl border p-4 mb-4">
            <p class="font-semibold text-slate-700 mb-1">Jadwal rutin mingguan</p>
            <p class="text-xs text-slate-400 mb-3">Berlaku terus tiap minggu. Kosongkan hari yang Anda tak bisa.</p>
            <div v-for="(hari, wd) in HARI" :key="wd" class="py-2 border-t first:border-t-0">
              <div class="flex items-center justify-between mb-1">
                <span class="text-sm font-medium" :class="pola[wd].length ? 'text-slate-700' : 'text-slate-400'">{{ hari }}</span>
                <button @click="tambahRentang(wd)" class="text-xs text-teal-700 bg-teal-50 hover:bg-teal-100 rounded px-2 py-1">+ Jam</button>
              </div>
              <p v-if="!pola[wd].length" class="text-xs text-slate-400">tidak tersedia</p>
              <div v-for="(r, i) in pola[wd]" :key="i" class="flex items-center gap-2 mb-1.5">
                <input v-model="r.start_time" type="time" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm" />
                <span class="text-slate-400 text-sm">–</span>
                <input v-model="r.end_time" type="time" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm" />
                <button @click="hapusRentang(wd, i)" class="text-red-500 text-xs px-1.5">✕</button>
              </div>
            </div>
            <button @click="simpanPola" :disabled="savingPola"
              class="mt-3 w-full py-2.5 rounded-lg bg-teal-600 hover:bg-teal-700 text-white font-medium disabled:opacity-50">
              {{ savingPola ? 'Menyimpan…' : 'Simpan Jadwal Rutin' }}
            </button>
            <p v-if="savedMsg" class="text-sm text-center mt-2" :class="savedMsg.includes('✓') ? 'text-emerald-600' : 'text-red-600'">{{ savedMsg }}</p>
          </div>

          <!-- Pengecualian tanggal -->
          <div class="bg-white rounded-xl border p-4">
            <p class="font-semibold text-slate-700 mb-1">Tanggal khusus</p>
            <p class="text-xs text-slate-400 mb-3">Menimpa jadwal rutin — untuk tanggal Anda berhalangan, atau justru bisa di luar jam biasa.</p>

            <div v-if="exceptions.length" class="mb-3 space-y-1.5">
              <div v-for="e in exceptions" :key="e.id" class="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-2">
                <span class="text-sm">
                  <span class="text-slate-700">{{ fmtDate(e.date) }}</span>
                  <span v-if="e.available" class="text-teal-700"> · bisa {{ e.start_time }}–{{ e.end_time }}</span>
                  <span v-else class="text-red-600"> · libur seharian</span>
                </span>
                <button @click="hapusPengecualian(e)" class="text-red-500 text-xs">Hapus</button>
              </div>
            </div>

            <div class="space-y-2">
              <input v-model="excForm.date" type="date" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              <div class="flex gap-3 text-sm">
                <label class="flex items-center gap-1.5 cursor-pointer"><input type="radio" :value="false" v-model="excForm.available" class="accent-red-600" /> Libur seharian</label>
                <label class="flex items-center gap-1.5 cursor-pointer"><input type="radio" :value="true" v-model="excForm.available" class="accent-teal-600" /> Bisa, jam tertentu</label>
              </div>
              <div v-if="excForm.available" class="flex items-center gap-2">
                <input v-model="excForm.start_time" type="time" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm" />
                <span class="text-slate-400 text-sm">–</span>
                <input v-model="excForm.end_time" type="time" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm" />
              </div>
              <p v-if="excErr" class="text-sm text-red-600">{{ excErr }}</p>
              <button @click="tambahPengecualian" :disabled="excBusy"
                class="w-full py-2 rounded-lg bg-slate-700 hover:bg-slate-800 text-white text-sm font-medium disabled:opacity-50">
                {{ excBusy ? 'Menyimpan…' : 'Tambah Tanggal Khusus' }}
              </button>
            </div>
          </div>
        </div>

        <!-- ============ JADWAL SAYA ============ -->
        <template v-if="tab === 'jadwal'">
        <div class="bg-white rounded-xl border p-4 mb-4 flex justify-between items-center">
          <div>
            <p class="text-xs text-slate-400">Sesi mendatang</p>
            <p class="text-xl font-bold text-slate-800">{{ sessions.length }} sesi</p>
          </div>
          <div class="text-right">
            <p class="text-xs text-slate-400">Total jam</p>
            <p class="text-xl font-bold text-teal-700">{{ fmtJam(totalHours) }}</p>
          </div>
        </div>

        <p v-if="!sessions.length" class="bg-white rounded-xl border p-6 text-center text-slate-400 text-sm">
          Belum ada jadwal coaching mendatang.
        </p>

        <div v-for="g in byDate" :key="g.date" class="mb-4">
          <p class="text-sm font-semibold text-slate-600 mb-2">
            {{ fmtDate(g.date) }}
            <span v-if="isToday(g.date)" class="ml-1 text-[10px] bg-teal-100 text-teal-700 rounded px-1.5 py-0.5 align-middle">HARI INI</span>
          </p>
          <div class="space-y-2">
            <div v-for="(s, i) in g.items" :key="i" class="bg-white rounded-xl border p-3">
              <div class="flex justify-between items-start gap-3">
                <div class="min-w-0">
                  <p class="font-bold text-slate-800">{{ s.start_time }}–{{ s.end_time }}</p>
                  <p class="text-sm text-slate-500">{{ s.facility_name }}<span v-if="s.persons"> · {{ s.persons }} peserta</span></p>
                </div>
                <span v-if="s.hours" class="text-xs bg-slate-100 text-slate-600 rounded px-2 py-1 shrink-0">{{ fmtJam(s.hours) }}</span>
              </div>
              <div v-if="s.customer_name || s.customer_phone" class="mt-2 pt-2 border-t flex items-center justify-between gap-2">
                <span class="text-sm text-slate-600 truncate">{{ s.customer_name || 'Tanpa nama' }}</span>
                <a v-if="waLink(s.customer_phone)" :href="waLink(s.customer_phone)" target="_blank" rel="noopener"
                  class="text-xs bg-emerald-50 text-emerald-700 rounded-lg px-2.5 py-1.5 font-medium shrink-0 hover:bg-emerald-100">
                  Chat WhatsApp
                </a>
              </div>
            </div>
          </div>
        </div>

        </template>

        <p class="text-xs text-slate-400 mt-6 border-t pt-3">
          🔒 Tautan ini pribadi &amp; berisi kontak murid — mohon jangan dibagikan ke siapa pun.
        </p>
      </template>
    </main>
  </div>
</template>
