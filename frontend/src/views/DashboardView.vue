<script setup>
import { onMounted, ref, computed, nextTick } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import Chart from 'chart.js/auto'

const auth = useAuthStore()
const venues = ref([])
const loading = ref(true)
const error = ref('')
let chart = null

const totalVenues = computed(() => venues.value.length)
const activeVenues = computed(() => venues.value.filter((v) => v.active).length)
const totalCapacity = computed(() =>
  venues.value.reduce((sum, v) => sum + (v.capacity || 0), 0),
)
const byType = computed(() => {
  const m = {}
  venues.value.forEach((v) => (m[v.type] = (m[v.type] || 0) + 1))
  return m
})

const stats = computed(() => [
  { label: 'Total Venue', value: totalVenues.value, icon: '🏟️', color: 'bg-brand-500' },
  { label: 'Venue Aktif', value: activeVenues.value, icon: '✅', color: 'bg-emerald-500' },
  { label: 'Total Kapasitas', value: totalCapacity.value.toLocaleString('id-ID'), icon: '👥', color: 'bg-amber-500' },
  { label: 'Tipe Venue', value: Object.keys(byType.value).length, icon: '🏷️', color: 'bg-violet-500' },
])

function renderChart() {
  const el = document.getElementById('venueChart')
  if (!el) return
  if (chart) chart.destroy()
  const labels = Object.keys(byType.value)
  chart = new Chart(el, {
    type: 'doughnut',
    data: {
      labels: labels.map((l) => l.replace(/_/g, ' ')),
      datasets: [
        {
          data: labels.map((l) => byType.value[l]),
          backgroundColor: ['#1877cc', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4'],
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom' } },
    },
  })
}

onMounted(async () => {
  try {
    const { data } = await client.get('/venues')
    venues.value = data.venues
  } catch (e) {
    error.value = 'Gagal memuat data venue.'
  } finally {
    loading.value = false
  }
  // render SETELAH loading=false agar <canvas> sudah ada di DOM
  if (!error.value) {
    await nextTick()
    renderChart()
  }
})
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-800">Selamat datang, {{ auth.user?.username }} 👋</h1>
    <p class="text-slate-500 mt-1">Ringkasan sistem manajemen venue ASP Sports.</p>

    <div v-if="loading" class="mt-8 text-slate-400">Memuat data…</div>
    <p v-else-if="error" class="mt-8 text-red-600">{{ error }}</p>

    <template v-else>
      <!-- Stat cards -->
      <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mt-6">
        <div
          v-for="s in stats"
          :key="s.label"
          class="bg-white rounded-xl shadow-sm border p-5 flex items-center gap-4"
        >
          <div :class="[s.color, 'h-12 w-12 rounded-lg flex items-center justify-center text-2xl']">
            {{ s.icon }}
          </div>
          <div>
            <p class="text-2xl font-bold text-slate-800">{{ s.value }}</p>
            <p class="text-sm text-slate-500">{{ s.label }}</p>
          </div>
        </div>
      </div>

      <!-- Chart + recent -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-6">
        <div class="bg-white rounded-xl shadow-sm border p-6 lg:col-span-1">
          <h3 class="font-semibold text-slate-700 mb-4">Venue per Tipe</h3>
          <div class="relative h-64"><canvas id="venueChart"></canvas></div>
        </div>

        <div class="bg-white rounded-xl shadow-sm border p-6 lg:col-span-2">
          <h3 class="font-semibold text-slate-700 mb-4">Daftar Venue</h3>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-left text-slate-400 border-b">
                  <th class="pb-2 font-medium">Kode</th>
                  <th class="pb-2 font-medium">Nama</th>
                  <th class="pb-2 font-medium">Tipe</th>
                  <th class="pb-2 font-medium text-right">Kapasitas</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="v in venues.slice(0, 6)" :key="v.id" class="border-b last:border-0">
                  <td class="py-2 font-mono text-slate-500">{{ v.code }}</td>
                  <td class="py-2 text-slate-700">{{ v.name }}</td>
                  <td class="py-2">
                    <span class="text-xs bg-slate-100 text-slate-600 rounded px-2 py-0.5">
                      {{ v.type.replace(/_/g, ' ') }}
                    </span>
                  </td>
                  <td class="py-2 text-right text-slate-600">{{ v.capacity?.toLocaleString('id-ID') }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
