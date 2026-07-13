<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '../api/client'

const permissions = ref([])
const roles = ref([])
const grants = ref({})           // { role: [codes] }
const loading = ref(false)
const toast = ref('')
const saving = ref('')            // "role:code" yang sedang disimpan

function flash(m) { toast.value = m; setTimeout(() => (toast.value = ''), 2000) }

// kelompokkan izin per kategori (urutan sesuai katalog backend)
const grouped = computed(() => {
  const out = []
  for (const p of permissions.value) {
    let g = out.find((x) => x.category === p.category)
    if (!g) { g = { category: p.category, items: [] }; out.push(g) }
    g.items.push(p)
  }
  return out
})

function has(role, code) { return (grants.value[role] || []).includes(code) }

async function load() {
  loading.value = true
  try {
    const { data } = await client.get('/admin/permissions')
    permissions.value = data.permissions
    roles.value = data.roles
    grants.value = data.grants
  } finally { loading.value = false }
}

async function toggle(role, code) {
  const granted = !has(role, code)
  saving.value = `${role}:${code}`
  // optimistik
  const list = grants.value[role] ? [...grants.value[role]] : []
  grants.value[role] = granted ? [...list, code] : list.filter((c) => c !== code)
  try {
    await client.post('/admin/permissions', { role, code, granted })
    flash('Izin diperbarui')
  } catch (e) {
    // rollback
    const l2 = grants.value[role] || []
    grants.value[role] = granted ? l2.filter((c) => c !== code) : [...l2, code]
    alert(e?.response?.data?.message || 'Gagal menyimpan.')
  } finally { saving.value = '' }
}
onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center gap-2 mb-1">
      <h1 class="text-2xl font-bold text-slate-800">Hak Akses (RBAC)</h1>
      <span class="text-xs bg-brand-50 text-brand-700 px-2 py-0.5 rounded-full font-medium">🔑 Admin</span>
    </div>
    <p class="text-slate-500 mb-5">Atur izin tiap role dengan mencentang. Perubahan langsung berlaku. <b>Administrator</b> selalu punya semua izin.</p>

    <div v-if="loading" class="text-slate-400">Memuat…</div>
    <div v-else class="bg-white rounded-xl shadow-sm border overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-slate-500">
          <tr>
            <th class="px-4 py-3 font-medium text-left sticky left-0 bg-slate-50 min-w-[280px]">Izin</th>
            <th class="px-3 py-3 font-medium text-center text-slate-400">Admin</th>
            <th v-for="r in roles" :key="r.code" class="px-3 py-3 font-medium text-center whitespace-nowrap">{{ r.label }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="g in grouped" :key="g.category">
            <tr class="bg-slate-100/70">
              <td :colspan="roles.length + 2" class="px-4 py-1.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">{{ g.category }}</td>
            </tr>
            <tr v-for="p in g.items" :key="p.code" class="border-t hover:bg-slate-50/60">
              <td class="px-4 py-2 sticky left-0 bg-white">
                <div class="text-slate-700">{{ p.label }}</div>
                <div class="text-xs text-slate-400 font-mono">{{ p.code }}</div>
              </td>
              <td class="px-3 py-2 text-center text-emerald-500" title="Administrator selalu punya semua izin">✓</td>
              <td v-for="r in roles" :key="r.code" class="px-3 py-2 text-center">
                <input type="checkbox" :checked="has(r.code, p.code)" :disabled="saving === `${r.code}:${p.code}`"
                  @change="toggle(r.code, p.code)"
                  class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500 cursor-pointer disabled:opacity-40" />
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <p class="text-xs text-slate-400 mt-4">
      Catatan: cakupan data (venue/area) tetap otomatis — Manager hanya venue-nya, Admin Unit hanya areanya. Izin di sini mengatur <i>fitur apa</i> yang boleh diakses, bukan <i>venue mana</i>.
    </p>

    <div v-if="toast" class="fixed bottom-6 right-6 bg-slate-800 text-white text-sm px-4 py-2 rounded-lg shadow-lg">{{ toast }}</div>
  </div>
</template>
