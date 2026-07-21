<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isAdminUnit = computed(() => auth.user?.role === 'admin_unit')
const isManager = computed(() => auth.user?.role === 'manager_unit')

const venues = ref([])
const venueId = ref(null)
const toast = ref('')
function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2500) }
function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }

const tab = ref('station')
const TIERS = [
  { value: 'reguler', label: 'Reguler' },
  { value: 'vip', label: 'VIP' },
  { value: 'simulator', label: 'Simulator' },
]
const tierLabel = (t) => TIERS.find((x) => x.value === t)?.label || t

async function loadVenues() {
  const { data } = await client.get('/venues')
  venues.value = data.venues
  if (isManager.value) venues.value = venues.value.filter((x) => x.id === auth.user?.venue_id)
  else if (isAdminUnit.value) venues.value = venues.value.filter((x) => x.area_id === auth.user?.area_id)
  if (venues.value.length && !venueId.value) venueId.value = venues.value[0].id
}

// ---------------- STATION ----------------
const stations = ref([])
const showStation = ref(false)
const editingStation = ref(null)
const stationForm = ref({})
const stationErr = ref('')
const savingStation = ref(false)

async function loadStations() {
  if (!venueId.value) return
  const { data } = await client.get('/stations', { params: { venue_id: venueId.value } })
  stations.value = data.stations
}
function openStation(s = null) {
  editingStation.value = s
  stationForm.value = s
    ? { code: s.code, name: s.name, tier: s.tier, hourly_rate: s.hourly_rate, is_active: s.is_active }
    : { code: '', name: '', tier: 'reguler', hourly_rate: 0, is_active: true }
  stationErr.value = ''; showStation.value = true
}
async function saveStation() {
  savingStation.value = true; stationErr.value = ''
  try {
    if (editingStation.value) await client.put(`/stations/${editingStation.value.id}`, stationForm.value)
    else await client.post('/stations', { ...stationForm.value, venue_id: venueId.value })
    showStation.value = false; await loadStations(); flash('Station disimpan')
  } catch (e) { stationErr.value = e?.response?.data?.message || 'Gagal.' } finally { savingStation.value = false }
}
async function removeStation(s) {
  if (!window.confirm(`Hapus station "${s.name}"?`)) return
  try { await client.delete(`/stations/${s.id}`); await loadStations(); flash('Station dihapus') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal menghapus.') }
}

// ---------------- ADD-ON ----------------
const addons = ref([])
const showAddon = ref(false)
const editingAddon = ref(null)
const addonForm = ref({})
const addonErr = ref('')
const savingAddon = ref(false)

async function loadAddons() {
  if (!venueId.value) return
  const { data } = await client.get('/stations/addons', { params: { venue_id: venueId.value } })
  addons.value = data.addons
}
function openAddon(a = null) {
  editingAddon.value = a
  addonForm.value = a ? { name: a.name, hourly_rate: a.hourly_rate, is_active: a.is_active } : { name: '', hourly_rate: 0, is_active: true }
  addonErr.value = ''; showAddon.value = true
}
async function saveAddon() {
  savingAddon.value = true; addonErr.value = ''
  try {
    if (editingAddon.value) await client.put(`/stations/addons/${editingAddon.value.id}`, addonForm.value)
    else await client.post('/stations/addons', { ...addonForm.value, venue_id: venueId.value })
    showAddon.value = false; await loadAddons(); flash('Add-on disimpan')
  } catch (e) { addonErr.value = e?.response?.data?.message || 'Gagal.' } finally { savingAddon.value = false }
}
async function removeAddon(a) {
  if (!window.confirm(`Hapus add-on "${a.name}"?`)) return
  try { await client.delete(`/stations/addons/${a.id}`); await loadAddons(); flash('Add-on dihapus') }
  catch (e) { alert(e?.response?.data?.message || 'Gagal menghapus.') }
}

function reloadTab() {
  if (tab.value === 'station') loadStations()
  else loadAddons()
}
onMounted(async () => { await loadVenues(); await reloadTab() })
watch(venueId, reloadTab)
watch(tab, reloadTab)
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-6">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">Station Gaming</h1>
        <p class="text-slate-500 mt-1">Kelola station (PS/PC/simulator) dan add-on perangkat tambahan untuk venue arena esport.</p>
      </div>
      <select v-if="!isManager" v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
        <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
      </select>
    </div>

    <div class="flex gap-1 mb-4 border-b">
      <button @click="tab = 'station'" :class="tab === 'station' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Station</button>
      <button @click="tab = 'addon'" :class="tab === 'addon' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Add-on</button>
    </div>

    <!-- ============ STATION ============ -->
    <div v-if="tab === 'station'">
      <div class="flex justify-end mb-3">
        <button @click="openStation()" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Station</button>
      </div>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-4 py-3 font-medium">Kode</th><th class="px-4 py-3 font-medium">Nama</th>
              <th class="px-4 py-3 font-medium">Tier</th><th class="px-4 py-3 font-medium text-right">Tarif/Jam</th>
              <th class="px-4 py-3 font-medium text-center">Status</th><th class="px-4 py-3"></th>
            </tr></thead>
            <tbody>
              <tr v-if="!stations.length"><td colspan="6" class="px-4 py-8 text-center text-slate-400">Belum ada station.</td></tr>
              <tr v-for="s in stations" :key="s.id" class="border-t hover:bg-slate-50">
                <td class="px-4 py-3 font-mono text-xs text-slate-500">{{ s.code }}</td>
                <td class="px-4 py-3 font-medium text-slate-700">{{ s.name }}</td>
                <td class="px-4 py-3 text-slate-500 capitalize">{{ tierLabel(s.tier) }}</td>
                <td class="px-4 py-3 text-right">{{ rupiah(s.hourly_rate) }}</td>
                <td class="px-4 py-3 text-center">
                  <span :class="s.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="text-xs rounded-full px-2 py-0.5">{{ s.is_active ? 'Aktif' : 'Nonaktif' }}</span>
                </td>
                <td class="px-4 py-3 text-right whitespace-nowrap">
                  <button @click="openStation(s)" class="text-brand-600 text-sm hover:underline mr-3">Edit</button>
                  <button @click="removeStation(s)" class="text-red-500 text-sm hover:underline">Hapus</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ============ ADD-ON ============ -->
    <div v-else>
      <div class="flex justify-end mb-3">
        <button @click="openAddon()" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-4 py-2 font-medium">+ Add-on</button>
      </div>
      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-4 py-3 font-medium">Nama</th><th class="px-4 py-3 font-medium text-right">Tarif/Jam</th>
              <th class="px-4 py-3 font-medium text-center">Status</th><th class="px-4 py-3"></th>
            </tr></thead>
            <tbody>
              <tr v-if="!addons.length"><td colspan="4" class="px-4 py-8 text-center text-slate-400">Belum ada add-on.</td></tr>
              <tr v-for="a in addons" :key="a.id" class="border-t hover:bg-slate-50">
                <td class="px-4 py-3 font-medium text-slate-700">{{ a.name }}</td>
                <td class="px-4 py-3 text-right">{{ rupiah(a.hourly_rate) }}</td>
                <td class="px-4 py-3 text-center">
                  <span :class="a.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="text-xs rounded-full px-2 py-0.5">{{ a.is_active ? 'Aktif' : 'Nonaktif' }}</span>
                </td>
                <td class="px-4 py-3 text-right whitespace-nowrap">
                  <button @click="openAddon(a)" class="text-brand-600 text-sm hover:underline mr-3">Edit</button>
                  <button @click="removeAddon(a)" class="text-red-500 text-sm hover:underline">Hapus</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Station modal -->
    <div v-if="showStation" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-sm rounded-2xl p-5">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-slate-800">{{ editingStation ? 'Edit Station' : 'Station Baru' }}</h3>
          <button @click="showStation = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <div class="space-y-3">
          <div><label class="block text-xs text-slate-500 mb-1">Kode</label>
            <input v-model="stationForm.code" placeholder="mis. ST-01" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Nama</label>
            <input v-model="stationForm.name" placeholder="mis. Station 1" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Tier</label>
            <select v-model="stationForm.tier" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option v-for="t in TIERS" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select></div>
          <div><label class="block text-xs text-slate-500 mb-1">Tarif per jam</label>
            <input v-model.number="stationForm.hourly_rate" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <label v-if="editingStation" class="flex items-center gap-2 text-sm text-slate-600">
            <input v-model="stationForm.is_active" type="checkbox" /> Aktif
          </label>
          <p v-if="stationErr" class="text-sm text-red-600">{{ stationErr }}</p>
          <button @click="saveStation" :disabled="savingStation" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">
            {{ savingStation ? 'Menyimpan…' : 'Simpan' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Add-on modal -->
    <div v-if="showAddon" class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white w-full max-w-sm rounded-2xl p-5">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-slate-800">{{ editingAddon ? 'Edit Add-on' : 'Add-on Baru' }}</h3>
          <button @click="showAddon = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <div class="space-y-3">
          <div><label class="block text-xs text-slate-500 mb-1">Nama</label>
            <input v-model="addonForm.name" placeholder="mis. Stick Tambahan, VR Headset" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label class="block text-xs text-slate-500 mb-1">Tarif per jam</label>
            <input v-model.number="addonForm.hourly_rate" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <p class="text-xs text-slate-400">Ditagih per jam mengikuti durasi sesi station-nya (bukan flat sekali bayar).</p>
          <label v-if="editingAddon" class="flex items-center gap-2 text-sm text-slate-600">
            <input v-model="addonForm.is_active" type="checkbox" /> Aktif
          </label>
          <p v-if="addonErr" class="text-sm text-red-600">{{ addonErr }}</p>
          <button @click="saveAddon" :disabled="savingAddon" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">
            {{ savingAddon ? 'Menyimpan…' : 'Simpan' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="toast" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
