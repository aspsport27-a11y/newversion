<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import axios from 'axios'

const api = axios.create({ baseURL: '/api/public' })

// step: 'venues' | 'facilities' | 'schedule'
const step = ref('venues')
const loading = ref(false)
const errorMsg = ref('')

const venues = ref([])
const facilities = ref([])
const slots = ref([])

const selectedVenue = ref(null)
const selectedFacility = ref(null)
const selectedDate = ref(new Date().toISOString().slice(0, 10))

const dateOptions = computed(() => {
  const out = []
  for (let i = 0; i < 14; i++) {
    const d = new Date()
    d.setDate(d.getDate() + i)
    out.push(d.toISOString().slice(0, 10))
  }
  return out
})

function fmtDateLabel(iso) {
  const d = new Date(iso + 'T00:00:00')
  const hari = ['Min', 'Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab'][d.getDay()]
  return `${hari} ${d.getDate()}/${d.getMonth() + 1}`
}

async function loadVenues() {
  loading.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.get('/venues')
    venues.value = data.venues
  } catch (e) {
    errorMsg.value = 'Gagal memuat daftar venue. Coba lagi beberapa saat.'
  } finally {
    loading.value = false
  }
}

async function openVenue(v) {
  selectedVenue.value = v
  loading.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.get('/facilities', { params: { venue_id: v.id } })
    facilities.value = data.facilities
    step.value = 'facilities'
  } catch (e) {
    errorMsg.value = 'Gagal memuat lapangan venue ini.'
  } finally {
    loading.value = false
  }
}

async function openFacility(f) {
  selectedFacility.value = f
  selectedDate.value = new Date().toISOString().slice(0, 10)
  step.value = 'schedule'
  await loadSchedule()
}

async function loadSchedule() {
  if (!selectedFacility.value) return
  loading.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.get('/schedule', {
      params: { facility_id: selectedFacility.value.id, date: selectedDate.value },
    })
    slots.value = data.slots
  } catch (e) {
    errorMsg.value = 'Gagal memuat jadwal. Coba lagi beberapa saat.'
    slots.value = []
  } finally {
    loading.value = false
  }
}

watch(selectedDate, () => {
  if (step.value === 'schedule') loadSchedule()
})

function backToVenues() {
  step.value = 'venues'
  selectedVenue.value = null
  facilities.value = []
}

function backToFacilities() {
  step.value = 'facilities'
  selectedFacility.value = null
  slots.value = []
}

function waLink(phone, text) {
  if (!phone) return null
  let digits = phone.replace(/\D/g, '')
  if (!digits) return null
  if (digits.startsWith('0')) digits = '62' + digits.slice(1)
  else if (!digits.startsWith('62')) digits = '62' + digits
  return `https://wa.me/${digits}?text=${encodeURIComponent(text)}`
}

function bookLink(slot) {
  const v = selectedVenue.value
  const f = selectedFacility.value
  const text = `Halo, saya mau booking ${f.name} (${v.name}) tanggal ${selectedDate.value} jam ${slot.start_time}-${slot.end_time}.`
  return waLink(v.phone, text)
}

onMounted(loadVenues)
</script>

<template>
  <div class="min-h-full">
    <header class="bg-brand-900 text-white">
      <div class="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3">
        <img src="/asp-logo.png" alt="ASP Sports" class="h-8" style="filter: brightness(0) invert(1)" />
        <div>
          <p class="font-semibold leading-tight">Jadwal Lapangan</p>
          <p class="text-xs text-brand-100 leading-tight">Cek ketersediaan &amp; booking via WhatsApp</p>
        </div>
      </div>
    </header>

    <main class="max-w-3xl mx-auto px-4 py-6">
      <p v-if="errorMsg" class="mb-4 rounded-lg bg-red-50 text-red-700 text-sm px-4 py-3">{{ errorMsg }}</p>

      <!-- STEP 1: pilih venue -->
      <div v-if="step === 'venues'">
        <h2 class="text-lg font-semibold text-slate-700 mb-3">Pilih Venue</h2>
        <div v-if="loading" class="text-slate-400 text-sm">Memuat...</div>
        <div v-else class="grid gap-3 sm:grid-cols-2">
          <button
            v-for="v in venues" :key="v.id" @click="openVenue(v)"
            class="text-left rounded-xl bg-white border border-slate-200 p-4 hover:border-brand-500 hover:shadow-md transition"
          >
            <p class="font-semibold text-slate-800">{{ v.name }}</p>
            <p class="text-xs text-slate-400 mt-0.5">{{ v.type }} · {{ v.area || '-' }}</p>
            <p class="text-xs text-slate-400 mt-1">{{ v.address }}</p>
          </button>
        </div>
        <p v-if="!loading && !venues.length" class="text-slate-400 text-sm">Belum ada venue tersedia.</p>
      </div>

      <!-- STEP 2: pilih facility/lapangan -->
      <div v-else-if="step === 'facilities'">
        <button @click="backToVenues" class="text-sm text-brand-700 mb-3">&larr; Venue lain</button>
        <h2 class="text-lg font-semibold text-slate-700 mb-3">{{ selectedVenue?.name }} — Pilih Lapangan</h2>
        <div v-if="loading" class="text-slate-400 text-sm">Memuat...</div>
        <div v-else class="grid gap-3 sm:grid-cols-2">
          <button
            v-for="f in facilities" :key="f.id" @click="openFacility(f)"
            class="text-left rounded-xl bg-white border border-slate-200 p-4 hover:border-brand-500 hover:shadow-md transition"
          >
            <p class="font-semibold text-slate-800">{{ f.name }}</p>
            <p class="text-xs text-slate-400 mt-0.5">{{ f.type }} · Rp {{ f.hourly_rate.toLocaleString('id-ID') }}/jam</p>
            <p class="text-xs text-slate-400 mt-1">Buka {{ f.open_time }} – {{ f.close_time }}</p>
          </button>
        </div>
        <p v-if="!loading && !facilities.length" class="text-slate-400 text-sm">Belum ada lapangan di venue ini.</p>
      </div>

      <!-- STEP 3: tanggal + grid slot -->
      <div v-else-if="step === 'schedule'">
        <button @click="backToFacilities" class="text-sm text-brand-700 mb-3">&larr; Lapangan lain</button>
        <h2 class="text-lg font-semibold text-slate-700 mb-1">{{ selectedFacility?.name }}</h2>
        <p class="text-xs text-slate-400 mb-3">{{ selectedVenue?.name }}</p>

        <div class="flex gap-2 overflow-x-auto pb-2 mb-4">
          <button
            v-for="d in dateOptions" :key="d" @click="selectedDate = d"
            :class="[
              'shrink-0 px-3 py-1.5 rounded-lg text-sm border transition',
              selectedDate === d ? 'bg-brand-600 text-white border-brand-600' : 'bg-white text-slate-600 border-slate-200 hover:border-brand-500',
            ]"
          >{{ fmtDateLabel(d) }}</button>
        </div>

        <div v-if="loading" class="text-slate-400 text-sm">Memuat jadwal...</div>
        <div v-else class="grid grid-cols-2 sm:grid-cols-3 gap-2">
          <div
            v-for="s in slots" :key="s.start_time"
            :class="[
              'rounded-lg border px-3 py-2.5 text-sm',
              s.status === 'available' ? 'bg-emerald-50 border-emerald-200' : 'bg-slate-100 border-slate-200 text-slate-400',
            ]"
          >
            <p class="font-medium">{{ s.start_time }}–{{ s.end_time }}</p>
            <p v-if="s.status === 'booked'" class="text-xs mt-1">Terisi</p>
            <a
              v-else :href="bookLink(s)" target="_blank" rel="noopener"
              class="inline-block text-xs mt-1 text-emerald-700 font-medium hover:underline"
            >Booking via WhatsApp &rarr;</a>
          </div>
        </div>
        <p v-if="!loading && !slots.length" class="text-slate-400 text-sm">Lapangan tutup / tidak ada jam operasional pada tanggal ini.</p>
      </div>
    </main>
  </div>
</template>
