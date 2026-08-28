<script setup>
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { RouterView, RouterLink, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'
import client from '../api/client'
import AskAiDialog from '../components/AskAiDialog.vue'

const auth = useAuthStore()
const router = useRouter()
const toastStore = useToastStore()
function flash(m) { toastStore.show(m) }
const sidebarOpen = ref(false)
const showAskAi = ref(false)
const showUserMenu = ref(false)

// Notifikasi hal-hal yg menunggu tindakan — Procurement (kind=sale), Procurement
// Ops (kind=ops), & Operasional/pengajuan dana. Endpoint list masing2 sudah scope
// venue/area sesuai role di backend, jadi tinggal hitung status non-final di sini.
const showNotif = ref(false)
const procPending = ref({ sale: 0, ops: 0 })
const opsPending = ref(0)
const otPending = ref({ lembur: 0, reward: 0, tambahan: 0 })
const OT_LABELS = { lembur: 'Lembur', reward: 'Reward', tambahan: 'Pekerjaan Tambahan' }
const otPendingRows = computed(() => Object.entries(otPending.value).filter(([, n]) => n > 0).map(([k, n]) => ({ key: k, label: OT_LABELS[k], count: n })))
const otPendingTotal = computed(() => Object.values(otPending.value).reduce((a, b) => a + b, 0))
const kasbonPending = ref(0)
const notifTotal = computed(() => procPending.value.sale + procPending.value.ops + opsPending.value + otPendingTotal.value + kasbonPending.value)
let procPendingTimer = null
async function loadProcPending() {
  if (auth.hasPerm('proc.view')) {
    try {
      const [sale, ops] = await Promise.all([
        client.get('/procurement/pos', { params: { kind: 'sale' } }),
        client.get('/procurement/pos', { params: { kind: 'ops' } }),
      ])
      const pending = (list) => list.filter((p) => p.status !== 'paid' && p.status !== 'rejected').length
      procPending.value = { sale: pending(sale.data.pos), ops: pending(ops.data.pos) }
    } catch (_) { /* diam-diam gagal, bukan fitur kritis */ }
  }
  if (auth.hasPerm('ops.view')) {
    try {
      const { data } = await client.get('/ops/requests')
      opsPending.value = data.requests.filter((r) => r.status !== 'disbursed' && r.status !== 'rejected').length
    } catch (_) { /* diam-diam gagal, bukan fitur kritis */ }
  }
  // pengajuan lembur/reward/tambahan menunggu persetujuan — relevan utk HO
  if (auth.hasPerm('payroll.approve')) {
    try {
      const { data } = await client.get('/payroll/overtime/pending-count')
      if (data.counts) otPending.value = data.counts
    } catch (_) { /* diam-diam gagal, bukan fitur kritis */ }
  }
  // pengajuan kasbon menunggu persetujuan HO
  if (auth.user?.role === 'admin' || auth.user?.role === 'head_office') {
    try {
      const { data } = await client.get('/admin/kasbon-requests/pending-count')
      kasbonPending.value = data.count
    } catch (_) { /* diam-diam gagal, bukan fitur kritis */ }
  }
}

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
    flash('Password berhasil diganti')
  } catch (e) { pwdErr.value = e?.response?.data?.message || 'Gagal mengganti password.' } finally { pwdBusy.value = false }
}

onMounted(async () => {
  try {
    // selalu tarik ulang user+permissions terbaru dari server saat app dimuat,
    // supaya perubahan RBAC (grant/revoke izin) langsung berlaku tanpa perlu
    // logout manual — sebelumnya cuma di-refresh kalau permissions kosong,
    // jadi izin baru yg ditambahkan ke role tak muncul sampai re-login
    await auth.fetchMe()
  } catch (_) {
    /* interceptor 401 akan redirect */
  }
  loadProcPending()
  procPendingTimer = setInterval(loadProcPending, 60000)
})
onUnmounted(() => clearInterval(procPendingTimer))

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
      { name: 'stations', label: 'Station Gaming', icon: '🎮', perm: 'station.manage', venueTypes: ['esport'] },
    ],
  },
  {
    label: 'HR',
    icon: '🧑‍💼',
    items: [
      { name: 'employees', label: 'Karyawan', icon: '👥', perm: 'hr.manage' },
      { name: 'attendance', label: 'Absensi', icon: '🕐', roles: ['admin', 'head_office', 'manager_unit'] },
      { name: 'payroll', label: 'Payroll', icon: '🧾', roles: ['admin', 'head_office', 'manager_unit'] },
    ],
  },
  {
    label: 'Transaksi',
    icon: '💳',
    items: [
      { name: 'bookings', label: 'Booking', icon: '📅', roles: ['admin', 'head_office', 'manager_unit'] },
      { name: 'events', label: 'Event', icon: '🏆', roles: ['admin', 'head_office', 'manager_unit'] },
      { name: 'operational', label: 'Operasional', icon: '💰', roles: ['admin', 'head_office', 'manager_unit', 'admin_unit'] },
      { name: 'procurement', label: 'Procurement', icon: '🛒', roles: ['admin', 'head_office', 'manager_unit', 'admin_unit'] },
      { name: 'procurement-ops', label: 'Procurement Ops', icon: '🧾', roles: ['admin', 'head_office', 'manager_unit', 'admin_unit'] },
      { name: 'treasury', label: 'Kas & Bank', icon: '🏦', roles: ADMINS },
    ],
  },
  {
    label: 'Laporan',
    icon: '📈',
    items: [
      { name: 'reports', label: 'Laporan Penjualan', icon: '📈', perm: 'report.sales' },
      { name: 'transactions', label: 'Riwayat Transaksi', icon: '🧾', roles: ['admin', 'head_office', 'manager_unit'] },
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
// venueTypes tambahan: manager_unit cuma boleh liat kalau venue-nya bertipe itu
// (mis. Station Gaming cuma utk manager venue esport, bukan manager venue lain)
function canSee(n) {
  if (n.venueTypes && auth.user?.role === 'manager_unit' && !n.venueTypes.includes(auth.user?.venue_type)) return false
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
          <div v-if="auth.hasPerm('proc.view') || auth.hasPerm('ops.view') || auth.hasPerm('payroll.approve') || ['admin','head_office'].includes(auth.user?.role)" class="relative">
            <div v-if="showNotif" class="fixed inset-0 z-30" @click="showNotif = false" />
            <button
              @click="showNotif = !showNotif"
              class="relative text-xl w-9 h-9 flex items-center justify-center rounded-lg hover:bg-slate-100 transition"
            >
              🔔
              <span
                v-if="notifTotal > 0"
                class="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] leading-[18px] font-semibold text-center"
              >
                {{ notifTotal > 99 ? '99+' : notifTotal }}
              </span>
            </button>
            <div
              v-if="showNotif"
              class="absolute right-0 mt-2 w-72 bg-white border rounded-xl shadow-lg z-40 overflow-hidden"
              @click.self="showNotif = false"
            >
              <div class="px-4 py-2.5 border-b text-xs font-semibold uppercase tracking-wide text-slate-400">
                Notifikasi
              </div>
              <div v-if="notifTotal === 0" class="px-4 py-6 text-sm text-slate-400 text-center">
                Tidak ada yang menunggu.
              </div>
              <template v-else>
                <RouterLink
                  v-if="procPending.sale > 0"
                  :to="{ name: 'procurement' }"
                  @click="showNotif = false"
                  class="flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition"
                  :class="{ 'border-b': procPending.ops > 0 || opsPending > 0 }"
                >
                  <span class="text-sm text-slate-700">🛒 Procurement</span>
                  <span class="text-xs bg-red-50 text-red-600 font-semibold rounded-full px-2 py-0.5">{{ procPending.sale }} menunggu</span>
                </RouterLink>
                <RouterLink
                  v-if="procPending.ops > 0"
                  :to="{ name: 'procurement-ops' }"
                  @click="showNotif = false"
                  class="flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition"
                  :class="{ 'border-b': opsPending > 0 }"
                >
                  <span class="text-sm text-slate-700">🧾 Procurement Ops</span>
                  <span class="text-xs bg-red-50 text-red-600 font-semibold rounded-full px-2 py-0.5">{{ procPending.ops }} menunggu</span>
                </RouterLink>
                <RouterLink
                  v-if="opsPending > 0"
                  :to="{ name: 'operational' }"
                  @click="showNotif = false"
                  class="flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition"
                  :class="{ 'border-b': otPendingTotal > 0 }"
                >
                  <span class="text-sm text-slate-700">💰 Operasional</span>
                  <span class="text-xs bg-red-50 text-red-600 font-semibold rounded-full px-2 py-0.5">{{ opsPending }} menunggu</span>
                </RouterLink>
                <RouterLink
                  v-for="(row, i) in otPendingRows"
                  :key="row.key"
                  :to="{ name: 'payroll', query: { tab: row.key } }"
                  @click="showNotif = false"
                  class="flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition"
                  :class="{ 'border-b': i < otPendingRows.length - 1 || kasbonPending > 0 }"
                >
                  <span class="text-sm text-slate-700">🕐 {{ row.label }}</span>
                  <span class="text-xs bg-red-50 text-red-600 font-semibold rounded-full px-2 py-0.5">{{ row.count }} menunggu</span>
                </RouterLink>
                <RouterLink
                  v-if="kasbonPending > 0"
                  :to="{ name: 'employees', query: { tab: 'kasbon' } }"
                  @click="showNotif = false"
                  class="flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition"
                >
                  <span class="text-sm text-slate-700">💵 Kasbon</span>
                  <span class="text-xs bg-red-50 text-red-600 font-semibold rounded-full px-2 py-0.5">{{ kasbonPending }} menunggu</span>
                </RouterLink>
              </template>
            </div>
          </div>
          <button
            @click="showAskAi = true"
            class="text-sm text-brand-700 bg-brand-50 hover:bg-brand-100 border border-brand-100 rounded-lg px-3 py-1.5 transition"
          >
            ✨ Ask AI
          </button>
          <div class="relative">
            <div v-if="showUserMenu" class="fixed inset-0 z-30" @click="showUserMenu = false" />
            <button
              @click="showUserMenu = !showUserMenu"
              class="flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-slate-100 transition"
            >
              <div class="text-right leading-tight">
                <p class="text-sm font-medium text-slate-700">{{ auth.user?.username }}</p>
                <p class="text-xs text-slate-400">{{ auth.roleLabel }}</p>
              </div>
              <div class="h-9 w-9 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center font-semibold uppercase">
                {{ (auth.user?.username || '?').charAt(0) }}
              </div>
            </button>
            <div
              v-if="showUserMenu"
              class="absolute right-0 mt-2 w-52 bg-white border rounded-xl shadow-lg z-40 overflow-hidden py-1"
            >
              <button
                v-if="auth.user?.role === 'admin'"
                @click="showUserMenu = false; openPwd()"
                class="w-full text-left flex items-center gap-2 px-4 py-2.5 text-sm text-slate-600 hover:bg-slate-50 transition"
              >
                🔒 Ganti Password
              </button>
              <button
                @click="showUserMenu = false; doLogout()"
                class="w-full text-left flex items-center gap-2 px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 transition"
              >
                🚪 Keluar
              </button>
            </div>
          </div>
        </div>
      </header>

      <AskAiDialog v-if="showAskAi" @close="showAskAi = false" />

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
