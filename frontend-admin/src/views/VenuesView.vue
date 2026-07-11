<script setup>
import { onMounted, ref, computed } from 'vue'
import client from '../api/client'

const venues = ref([])
const loading = ref(true)
const error = ref('')
const search = ref('')

const filtered = computed(() => {
  const q = search.value.toLowerCase().trim()
  if (!q) return venues.value
  return venues.value.filter(
    (v) =>
      v.name.toLowerCase().includes(q) ||
      v.code.toLowerCase().includes(q) ||
      v.type.toLowerCase().includes(q),
  )
})

onMounted(async () => {
  try {
    const { data } = await client.get('/venues')
    venues.value = data.venues
  } catch (e) {
    error.value = 'Gagal memuat data venue.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">Venue</h1>
        <p class="text-slate-500 mt-1">{{ venues.length }} unit venue terdaftar.</p>
      </div>
      <input
        v-model="search"
        type="search"
        placeholder="Cari venue…"
        class="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-100 outline-none"
      />
    </div>

    <div v-if="loading" class="mt-8 text-slate-400">Memuat data…</div>
    <p v-else-if="error" class="mt-8 text-red-600">{{ error }}</p>

    <div v-else class="mt-6 bg-white rounded-xl shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50">
            <tr class="text-left text-slate-500">
              <th class="px-4 py-3 font-medium">Kode</th>
              <th class="px-4 py-3 font-medium">Nama</th>
              <th class="px-4 py-3 font-medium">Tipe</th>
              <th class="px-4 py-3 font-medium">Kota</th>
              <th class="px-4 py-3 font-medium text-right">Kapasitas</th>
              <th class="px-4 py-3 font-medium text-center">Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="v in filtered" :key="v.id" class="border-t hover:bg-slate-50">
              <td class="px-4 py-3 font-mono text-slate-500">{{ v.code }}</td>
              <td class="px-4 py-3 font-medium text-slate-700">{{ v.name }}</td>
              <td class="px-4 py-3">
                <span class="text-xs bg-brand-50 text-brand-700 rounded px-2 py-0.5">
                  {{ v.type.replace(/_/g, ' ') }}
                </span>
              </td>
              <td class="px-4 py-3 text-slate-600">{{ v.city || '—' }}</td>
              <td class="px-4 py-3 text-right text-slate-600">{{ v.capacity?.toLocaleString('id-ID') }}</td>
              <td class="px-4 py-3 text-center">
                <span
                  :class="v.active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'"
                  class="text-xs rounded-full px-2 py-0.5"
                >
                  {{ v.active ? 'Aktif' : 'Nonaktif' }}
                </span>
              </td>
            </tr>
            <tr v-if="filtered.length === 0">
              <td colspan="6" class="px-4 py-8 text-center text-slate-400">Tidak ada venue cocok.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
