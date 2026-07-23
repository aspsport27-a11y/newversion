<script setup>
import { ref, onMounted, computed } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isManager = computed(() => auth.user?.role === 'manager_unit')
const canManage = computed(() => auth.hasPerm('hr.manage'))
const busy = ref(false)

const tab = ref('roster') // 'roster' | 'leave'
const venues = ref([])
const venueId = ref('')

// ---------- Roster (kehadiran 1 hari) ----------
const rosterDate = ref(new Date().toISOString().slice(0, 10))
const rosterRows = ref([])
const rosterSummary = ref({})
const rosterLoading = ref(false)
const statusFilter = ref('')
const nameSearch = ref('')

const STATUS = {
  hadir: ['Hadir', 'bg-emerald-100 text-emerald-700'],
  belum: ['Belum absen', 'bg-slate-100 text-slate-500'],
  alpha: ['Alpha', 'bg-red-100 text-red-600'],
  izin: ['Izin', 'bg-blue-100 text-blue-700'],
  sakit: ['Sakit', 'bg-amber-100 text-amber-700'],
  cuti: ['Cuti', 'bg-purple-100 text-purple-700'],
}
function stLabel(s) { return STATUS[s]?.[0] || s }
function stClass(s) { return STATUS[s]?.[1] || 'bg-slate-100 text-slate-500' }

async function loadVenues() {
  const { data } = await client.get('/admin/venues')
  venues.value = data.venues
}
async function loadRoster() {
  rosterLoading.value = true
  const params = { date: rosterDate.value }
  if (!isManager.value && venueId.value) params.venue_id = venueId.value
  try {
    const { data } = await client.get('/admin/attendance/roster', { params })
    rosterRows.value = data.rows
    rosterSummary.value = data.summary
  } finally { rosterLoading.value = false }
}
const rosterShown = computed(() => {
  let list = rosterRows.value
  if (statusFilter.value) list = list.filter((r) => r.att_status === statusFilter.value)
  const q = nameSearch.value.trim().toLowerCase()
  if (q) list = list.filter((r) => (r.name || '').toLowerCase().includes(q))
  return list
})

async function setLeave(row, status) {
  const emp = row.name
  const verb = status === 'clear' ? 'batalkan keterangan' : status
  if (!window.confirm(`Tandai ${emp} "${verb}" tanggal ${rosterDate.value}?`)) return
  busy.value = true
  try {
    await client.post('/admin/attendance/leave', {
      employee_id: row.employee_id, date: rosterDate.value, status,
    })
    await loadRoster()
  } catch (e) { alert(e?.response?.data?.message || 'Gagal.') } finally { busy.value = false }
}

// ---------- Laporan Izin/Sakit/Cuti ----------
const today = new Date().toISOString().slice(0, 10)
const firstOfMonth = today.slice(0, 8) + '01'
const lvFrom = ref(firstOfMonth)
const lvTo = ref(today)
const lvPerEmp = ref([])
const lvDetail = ref([])
const lvTotal = ref({})
const lvLoading = ref(false)
async function loadLeave() {
  lvLoading.value = true
  const params = { from: lvFrom.value, to: lvTo.value }
  if (!isManager.value && venueId.value) params.venue_id = venueId.value
  try {
    const { data } = await client.get('/admin/attendance/leave-report', { params })
    lvPerEmp.value = data.per_employee
    lvDetail.value = data.detail
    lvTotal.value = data.total
  } finally { lvLoading.value = false }
}

function switchTab(t) {
  tab.value = t
  if (t === 'roster') loadRoster()
  else loadLeave()
}

// ---------- Foto & lokasi ----------
const photoUrl = ref('')
const photoTitle = ref('')
async function openPhoto(row, which) {
  try {
    const { data } = await client.get(`/admin/attendance/${row.attendance_id}/photo/${which}`, { responseType: 'blob' })
    photoUrl.value = URL.createObjectURL(data)
    photoTitle.value = `${row.name} — Absen ${which === 'in' ? 'Masuk' : 'Pulang'}`
  } catch { alert('Foto tidak tersedia.') }
}
function closePhoto() { if (photoUrl.value) URL.revokeObjectURL(photoUrl.value); photoUrl.value = '' }
function shortAddr(full) { return full ? full.split(',').slice(0, 2).join(',').trim() : '' }

// ---------- Export ----------
function csvDownload(name, header, body) {
  const csv = [header, ...body].map((r) => r.map((c) => `"${String(c ?? '').replace(/"/g, '""')}"`).join(',')).join('\r\n')
  const url = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' }))
  const el = document.createElement('a'); el.href = url; el.download = name; el.click(); URL.revokeObjectURL(url)
}
function exportRoster() {
  csvDownload(`kehadiran-${rosterDate.value}.csv`,
    ['Tanggal', 'Nama', 'Posisi', 'Venue', 'Status', 'Masuk', 'Pulang', 'Jam Kerja'],
    rosterShown.value.map((r) => [rosterDate.value, r.name, r.position || '', r.venue_code || '',
      stLabel(r.att_status), r.check_in || '', r.check_out ? r.check_out + (r.out_next_day ? ' (+1hr)' : '') : '',
      r.work_hours != null ? r.work_hours : '']))
}
function exportLeave() {
  csvDownload(`izin-sakit-cuti-${lvFrom.value}_${lvTo.value}.csv`,
    ['Tanggal', 'Nama', 'Venue', 'Keterangan'],
    lvDetail.value.map((r) => [r.date, r.name, r.venue_code || '', r.status]))
}

onMounted(async () => { await loadVenues(); await loadRoster() })
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-800 mb-1">Absensi</h1>
    <p class="text-slate-500 mb-5">Kehadiran staff (absen PIN di terminal POS, waktu WITA). Shift malam yang pulang lewat tengah malam dihitung ke hari mulai kerja.</p>

    <!-- Tabs -->
    <div class="flex gap-1 mb-5 border-b">
      <button @click="switchTab('roster')" :class="tab === 'roster' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Kehadiran</button>
      <button @click="switchTab('leave')" :class="tab === 'leave' ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" class="px-4 py-2 border-b-2 font-medium text-sm">Izin / Sakit / Cuti</button>
    </div>

    <!-- ============ TAB KEHADIRAN (roster) ============ -->
    <template v-if="tab === 'roster'">
      <div class="bg-white rounded-xl shadow-sm border p-4 mb-4 flex flex-wrap items-end gap-3">
        <div><label class="block text-xs text-slate-500 mb-1">Tanggal</label>
          <input v-model="rosterDate" @change="loadRoster" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
        <div v-if="!isManager"><label class="block text-xs text-slate-500 mb-1">Venue</label>
          <select v-model="venueId" @change="loadRoster" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
            <option value="">Semua venue (cakupan saya)</option>
            <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
          </select></div>
        <div><label class="block text-xs text-slate-500 mb-1">Status</label>
          <select v-model="statusFilter" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
            <option value="">Semua status</option>
            <option value="belum">Belum absen</option><option value="hadir">Hadir</option>
            <option value="alpha">Alpha</option><option value="izin">Izin</option>
            <option value="sakit">Sakit</option><option value="cuti">Cuti</option>
          </select></div>
        <div><label class="block text-xs text-slate-500 mb-1">Cari nama</label>
          <input v-model="nameSearch" placeholder="Nama…" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
        <button @click="exportRoster" :disabled="!rosterShown.length" class="bg-emerald-600 hover:bg-emerald-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-40 ml-auto">📊 Excel</button>
      </div>

      <!-- Ringkasan status -->
      <div class="flex flex-wrap gap-2 mb-4">
        <span v-for="k in ['hadir','belum','alpha','izin','sakit','cuti']" :key="k"
          :class="stClass(k)" class="text-xs rounded-full px-3 py-1 font-medium">{{ stLabel(k) }}: {{ rosterSummary[k] || 0 }}</span>
      </div>

      <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 text-slate-500 text-left"><tr>
              <th class="px-4 py-2 font-medium">Nama</th>
              <th class="px-4 py-2 font-medium">Posisi</th>
              <th class="px-4 py-2 font-medium text-center">Status</th>
              <th class="px-4 py-2 font-medium text-center">Masuk</th>
              <th class="px-4 py-2 font-medium text-center">Pulang</th>
              <th class="px-4 py-2 font-medium">Lokasi</th>
              <th class="px-4 py-2 font-medium text-right">Jam</th>
              <th v-if="canManage" class="px-4 py-2 font-medium text-center">Keterangan</th>
            </tr></thead>
            <tbody>
              <tr v-if="rosterLoading"><td :colspan="canManage ? 8 : 7" class="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>
              <tr v-else-if="!rosterShown.length"><td :colspan="canManage ? 8 : 7" class="px-4 py-8 text-center text-slate-400">Tidak ada karyawan.</td></tr>
              <tr v-for="r in rosterShown" :key="r.employee_id" class="border-t">
                <td class="px-4 py-2 text-slate-700 font-medium">{{ r.name }}</td>
                <td class="px-4 py-2 text-slate-500 text-xs">{{ r.position || '—' }}</td>
                <td class="px-4 py-2 text-center"><span :class="stClass(r.att_status)" class="text-xs rounded-full px-2 py-0.5">{{ stLabel(r.att_status) }}</span></td>
                <td class="px-4 py-2 text-center whitespace-nowrap">
                  <span :class="r.check_in ? 'text-emerald-700' : 'text-slate-300'">{{ r.check_in || '—' }}</span>
                  <button v-if="r.has_in_photo" @click="openPhoto(r, 'in')" title="Lihat foto" class="ml-1">📷</button>
                </td>
                <td class="px-4 py-2 text-center whitespace-nowrap">
                  <span v-if="r.check_out" class="text-slate-700">{{ r.check_out }}<span v-if="r.out_next_day" class="text-[10px] text-amber-600"> (+1hr)</span></span>
                  <span v-else class="text-slate-300">—</span>
                  <button v-if="r.has_out_photo" @click="openPhoto(r, 'out')" title="Lihat foto" class="ml-1">📷</button>
                </td>
                <td class="px-4 py-2 text-xs max-w-[180px]">
                  <a v-if="r.check_in_location" :href="`https://www.google.com/maps?q=${r.check_in_location}`" target="_blank" rel="noopener" :title="r.check_in_address || ''" class="block text-brand-600 hover:underline truncate">📍 {{ shortAddr(r.check_in_address) || 'Masuk' }}</a>
                  <span v-else class="text-slate-300">—</span>
                </td>
                <td class="px-4 py-2 text-right text-slate-600">{{ r.work_hours != null ? r.work_hours : '—' }}</td>
                <td v-if="canManage" class="px-4 py-2 text-center whitespace-nowrap">
                  <template v-if="['izin','sakit','cuti'].includes(r.att_status)">
                    <button @click="setLeave(r, 'clear')" :disabled="busy" class="text-xs text-red-500 hover:underline disabled:opacity-50">Batal</button>
                  </template>
                  <template v-else-if="!r.check_in">
                    <button @click="setLeave(r, 'izin')" :disabled="busy" class="text-xs bg-blue-50 text-blue-700 rounded px-1.5 py-0.5 mr-1">Izin</button>
                    <button @click="setLeave(r, 'sakit')" :disabled="busy" class="text-xs bg-amber-50 text-amber-700 rounded px-1.5 py-0.5 mr-1">Sakit</button>
                    <button @click="setLeave(r, 'cuti')" :disabled="busy" class="text-xs bg-purple-50 text-purple-700 rounded px-1.5 py-0.5">Cuti</button>
                  </template>
                  <span v-else class="text-slate-300 text-xs">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- ============ TAB IZIN/SAKIT/CUTI (laporan) ============ -->
    <template v-else>
      <div class="bg-white rounded-xl shadow-sm border p-4 mb-4 flex flex-wrap items-end gap-3">
        <div><label class="block text-xs text-slate-500 mb-1">Dari</label>
          <input v-model="lvFrom" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
        <div><label class="block text-xs text-slate-500 mb-1">Sampai</label>
          <input v-model="lvTo" type="date" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
        <div v-if="!isManager"><label class="block text-xs text-slate-500 mb-1">Venue</label>
          <select v-model="venueId" class="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500">
            <option value="">Semua venue (cakupan saya)</option>
            <option v-for="v in venues" :key="v.id" :value="v.id">{{ v.code }} — {{ v.name }}</option>
          </select></div>
        <button @click="loadLeave" class="bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg px-5 py-2 font-medium">Terapkan</button>
        <button @click="exportLeave" :disabled="!lvDetail.length" class="bg-emerald-600 hover:bg-emerald-700 text-white text-sm rounded-lg px-4 py-2 font-medium disabled:opacity-40 ml-auto">📊 Excel</button>
      </div>

      <div class="flex flex-wrap gap-2 mb-4">
        <span class="text-xs rounded-full px-3 py-1 font-medium bg-blue-100 text-blue-700">Izin: {{ lvTotal.izin || 0 }} hari</span>
        <span class="text-xs rounded-full px-3 py-1 font-medium bg-amber-100 text-amber-700">Sakit: {{ lvTotal.sakit || 0 }} hari</span>
        <span class="text-xs rounded-full px-3 py-1 font-medium bg-purple-100 text-purple-700">Cuti: {{ lvTotal.cuti || 0 }} hari</span>
      </div>

      <div class="bg-white rounded-xl shadow-sm border overflow-hidden mb-5">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-2 font-medium">Nama</th><th class="px-4 py-2 font-medium">Venue</th>
            <th class="px-4 py-2 font-medium text-right">Izin</th><th class="px-4 py-2 font-medium text-right">Sakit</th><th class="px-4 py-2 font-medium text-right">Cuti</th>
          </tr></thead>
          <tbody>
            <tr v-if="lvLoading"><td colspan="5" class="px-4 py-6 text-center text-slate-400">Memuat…</td></tr>
            <tr v-else-if="!lvPerEmp.length"><td colspan="5" class="px-4 py-6 text-center text-slate-400">Tidak ada izin/sakit/cuti pada periode ini.</td></tr>
            <tr v-for="e in lvPerEmp" :key="e.employee_id" class="border-t">
              <td class="px-4 py-2 text-slate-700 font-medium">{{ e.name }}</td>
              <td class="px-4 py-2 text-slate-500">{{ e.venue_code || '—' }}</td>
              <td class="px-4 py-2 text-right">{{ e.izin }}</td>
              <td class="px-4 py-2 text-right">{{ e.sakit }}</td>
              <td class="px-4 py-2 text-right">{{ e.cuti }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="lvDetail.length" class="bg-white rounded-xl shadow-sm border overflow-hidden">
        <p class="text-xs font-medium text-slate-400 px-4 pt-3">Rincian per tanggal</p>
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-500 text-left"><tr>
            <th class="px-4 py-2 font-medium">Tanggal</th><th class="px-4 py-2 font-medium">Nama</th><th class="px-4 py-2 font-medium">Venue</th><th class="px-4 py-2 font-medium text-center">Keterangan</th>
          </tr></thead>
          <tbody>
            <tr v-for="(r, i) in lvDetail" :key="i" class="border-t">
              <td class="px-4 py-2 text-slate-500">{{ r.date }}</td>
              <td class="px-4 py-2 text-slate-700">{{ r.name }}</td>
              <td class="px-4 py-2 text-slate-500">{{ r.venue_code || '—' }}</td>
              <td class="px-4 py-2 text-center"><span :class="stClass(r.status)" class="text-xs rounded-full px-2 py-0.5">{{ stLabel(r.status) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- Foto absen -->
    <div v-if="photoUrl" class="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" @click.self="closePhoto">
      <div class="bg-white rounded-2xl p-4 max-w-sm w-full">
        <div class="flex justify-between items-center mb-2">
          <p class="text-sm font-medium text-slate-700">{{ photoTitle }}</p>
          <button @click="closePhoto" class="text-slate-400 text-xl">✕</button>
        </div>
        <img :src="photoUrl" alt="Foto absen" class="w-full rounded-lg" />
      </div>
    </div>
  </div>
</template>
