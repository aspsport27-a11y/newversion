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
        <div class="bg-white rounded-xl border p-4 mb-4 flex justify-between items-center">
          <div>
            <p class="text-xs text-slate-400">Sesi mendatang (60 hari)</p>
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

        <p class="text-xs text-slate-400 mt-6 border-t pt-3">
          🔒 Tautan ini pribadi &amp; berisi kontak murid — mohon jangan dibagikan ke siapa pun.
        </p>
      </template>
    </main>
  </div>
</template>
