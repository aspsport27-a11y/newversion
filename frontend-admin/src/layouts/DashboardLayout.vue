<script setup>
import { onMounted, ref, computed } from 'vue'
import { RouterView, RouterLink, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import client from '../api/client'

const auth = useAuthStore()
const router = useRouter()
const sidebarOpen = ref(false)

// Ganti password akun sendiri (semua role login-portal, termasuk super admin)
const showPwd = ref(false)
const pwdForm = ref({ old_password: '', new_password: '', confirm: '' })
const pwdErr = ref('')
const pwdBusy = ref(false)
function openPwd() { pwdForm.value = { old_password: '', new_password: '', confirm: '' }; pwdErr.value = ''; showPwd.value = true }
async function savePwd() {
  pwdErr.value = ''
  if (pwdForm.value.new_password.length < 8) { pwdErr.value = 'Password baru minimal 8 karakter'; return }
  if (pwdForm.value.new_password !== pwdForm.value.confirm) { pwdErr.value = 'Konfirmasi password tidak cocok'; return }
  pwdBusy.value = true
  try {
    await client.post('/auth/reset-password', {
      old_password: pwdForm.value.old_password,
      new_password: pwdForm.value.new_password,
    })
    showPwd.value = false
    alert('Password berhasil diganti.')
  } catch (e) { pwdErr.value = e?.response?.data?.message || 'Gagal mengganti password.' } finally { pwdBusy.value = false }
}

onMounted(async () => {
  try {
    // refresh juga bila permissions belum ada (sesi lama sebelum fitur izin)
    if (!auth.user || !auth.permissions.length) await auth.fetchMe()
  } catch (_) {
    /* interceptor 401 akan redirect */
  }
})

async function doLogout() {
  await auth.logout()
  router.push({ name: 'login' })
}

const ADMINS = ['admin', 'head_office']

// Dashboard tampil sendiri di atas (bukan bagian grup)
const topItem = { name: 'dashboard', label: 'Dashboard', icon: '📊', roles: ['admin', 'head_office', 'manager_unit'] }

// Sisanya dikelompokkan supaya sidebar tidak jadi daftar 18 item datar
const navGroups = [
  {
    label: 'Master Data',
    icon: '🗂️',
    items: [
      { name: 'venues', label: 'Venue', icon: '🏟️', roles: ADMINS },
      { name: 'areas', label: 'Area', icon: '🗺️', roles: ADMINS },
      { name: 'products', label: 'Produk', icon: '📦', perm: 'product.manage' },
      { name: 'promos', label: 'Promo', icon: '🎉', perm: 'promo.manage' },
      { name: 'facilities', label: 'Lapangan & Tiket', icon: '⚽', perm: 'facility.manage' },
    ],
  },
  {
    label: 'HR',
    icon: '🧑‍💼',
    items: [
      { name: 'employees', label: 'Karyawan', icon: '👥', roles: ['admin', 'head_office', 'manager_unit'] },
      { name: 'attendance', label: 'Absensi', icon: '🕐', roles: ['admin', 'head_office', 'manager_unit'] },
      { name: 'payroll', label: 'Payroll', icon: '🧾', roles: ['admin', 'head_office', 'manager_unit'] },
    ],
  },
  {
    label: 'Transaksi',
    icon: '💳',
    items: [
      { name: 'bookings', label: 'Booking', icon: '📅', roles: ADMINS },
      { name: 'operational', label: 'Operasional', icon: '💰', roles: ['admin', 'head_office', 'manager_unit', 'admin_unit'] },
      { name: 'procurement', label: 'Procurement', icon: '🛒', roles: ['admin', 'head_office', 'manager_unit', 'admin_unit'] },
      { name: 'treasury', label: 'Kas & Bank', icon: '🏦', roles: ADMINS },
    ],
  },
  {
    label: 'Laporan',
    icon: '📈',
    items: [
      { name: 'reports', label: 'Laporan Penjualan', icon: '📈', roles: ADMINS },
      { name: 'financial', label: 'Laporan Bisnis', icon: '💹', roles: ['admin', 'head_office', 'manager_unit'] },
      { name: 'management-report', label: 'Laporan Manajemen', icon: '🔐', roles: ['admin', 'head_office'] },
    ],
  },
  {
    label: 'Pengaturan',
    icon: '⚙️',
    items: [
      { name: 'setup', label: 'Setup Kasir', icon: '⚙️', perm: 'setup.manage' },
      { name: 'permissions', label: 'Hak Akses', icon: '🔑', roles: ['admin'] },
    ],
  },
]

// item bisa digembok pakai daftar role tetap (roles) ATAU izin RBAC configurable (perm)
function canSee(n) {
  if (n.perm) return auth.hasPerm(n.perm)
  return n.roles.includes(auth.user?.role)
}
const showTop = computed(() => canSee(topItem))
const visibleGroups = computed(() =>
  navGroups
    .map((g) => ({ ...g, items: g.items.filter(canSee) }))
    .filter((g) => g.items.length > 0),
)

// simpan grup mana yg dilipat (collapse) di localStorage; default semua terbuka
const collapsed = ref(new Set(JSON.parse(localStorage.getItem('nav_collapsed') || '[]')))
function toggleGroup(label) {
  if (collapsed.value.has(label)) collapsed.value.delete(label)
  else collapsed.value.add(label)
  localStorage.setItem('nav_collapsed', JSON.stringify([...collapsed.value]))
}
</script>

<template>
  <div class="min-h-full flex">
    <!-- Sidebar -->
    <aside
      :class="[
        'fixed lg:static inset-y-0 left-0 z-30 w-64 bg-brand-900 text-white transform transition-transform lg:translate-x-0',
        sidebarOpen ? 'translate-x-0' : '-translate-x-full',
      ]"
    >
      <div class="h-16 flex items-center px-6 border-b border-white/10">
        <img src="/asp-logo.png" alt="ASP Sports" class="h-7" style="filter: brightness(0) invert(1)" />
      </div>
      <nav class="p-4 space-y-1 overflow-y-auto" style="max-height: calc(100vh - 4rem)">
        <RouterLink
          v-if="showTop"
          :to="{ name: topItem.name }"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-brand-100 hover:bg-white/10 transition"
          active-class="bg-white/15 text-white font-medium"
          @click="sidebarOpen = false"
        >
          <span>{{ topItem.icon }}</span>{{ topItem.label }}
        </RouterLink>

        <div v-for="g in visibleGroups" :key="g.label" class="pt-2">
          <button
            @click="toggleGroup(g.label)"
            class="w-full flex items-center justify-between px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-brand-300 hover:text-white transition"
          >
            <span>{{ g.icon }} {{ g.label }}</span>
            <span :class="['transition-transform', collapsed.has(g.label) ? '-rotate-90' : '']">▾</span>
          </button>
          <div v-show="!collapsed.has(g.label)" class="space-y-1 mt-0.5">
            <RouterLink
              v-for="item in g.items"
              :key="item.name"
              :to="{ name: item.name }"
              class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-brand-100 hover:bg-white/10 transition"
              active-class="bg-white/15 text-white font-medium"
              @click="sidebarOpen = false"
            >
              <span>{{ item.icon }}</span>{{ item.label }}
            </RouterLink>
          </div>
        </div>
      </nav>
    </aside>

    <div
      v-if="sidebarOpen"
      class="fixed inset-0 bg-black/40 z-20 lg:hidden"
      @click="sidebarOpen = false"
    />

    <!-- Main -->
    <div class="flex-1 flex flex-col min-w-0">
      <header class="h-16 bg-white border-b flex items-center justify-between px-4 lg:px-8">
        <button class="lg:hidden text-2xl" @click="sidebarOpen = true">☰</button>
        <div class="flex-1" />
        <div class="flex items-center gap-3">
          <div class="text-right leading-tight">
            <p class="text-sm font-medium text-slate-700">{{ auth.user?.username }}</p>
            <p class="text-xs text-slate-400">{{ auth.roleLabel }}</p>
          </div>
          <div class="h-9 w-9 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center font-semibold uppercase">
            {{ (auth.user?.username || '?').charAt(0) }}
          </div>
          <button
            v-if="auth.user?.role === 'admin'"
            @click="openPwd"
            class="text-sm text-slate-500 hover:text-brand-600 border rounded-lg px-3 py-1.5 transition"
          >
            🔒 Ganti Password
          </button>
          <button
            @click="doLogout"
            class="text-sm text-slate-500 hover:text-red-600 border rounded-lg px-3 py-1.5 transition"
          >
            Keluar
          </button>
        </div>
      </header>

      <main class="flex-1 p-4 lg:p-8 overflow-auto">
        <RouterView />
      </main>
    </div>

    <!-- Ganti Password (akun sendiri) -->
    <div v-if="showPwd" class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" @click.self="showPwd = false">
      <div class="bg-white w-full max-w-sm rounded-2xl p-5">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-slate-800">Ganti Password</h3>
          <button @click="showPwd = false" class="text-slate-400 text-xl">✕</button>
        </div>
        <div class="space-y-3">
          <div>
            <label class="block text-xs text-slate-500 mb-1">Password lama</label>
            <input v-model="pwdForm.old_password" type="password" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Password baru (min. 8 karakter)</label>
            <input v-model="pwdForm.new_password" type="password" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Ulangi password baru</label>
            <input v-model="pwdForm.confirm" type="password" @keyup.enter="savePwd" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <p v-if="pwdErr" class="text-sm text-red-600">{{ pwdErr }}</p>
          <button @click="savePwd" :disabled="pwdBusy" class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-50">
            {{ pwdBusy ? 'Menyimpan…' : 'Simpan Password Baru' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
