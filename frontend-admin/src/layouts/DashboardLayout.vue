<script setup>
import { onMounted, ref, computed } from 'vue'
import { RouterView, RouterLink, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const sidebarOpen = ref(false)

onMounted(async () => {
  try {
    if (!auth.user) await auth.fetchMe()
  } catch (_) {
    /* interceptor 401 akan redirect */
  }
})

async function doLogout() {
  await auth.logout()
  router.push({ name: 'login' })
}

const ADMINS = ['admin', 'head_office']
const allNav = [
  { name: 'dashboard', label: 'Dashboard', icon: '📊', roles: ['admin', 'head_office', 'manager_unit'] },
  { name: 'venues', label: 'Venue', icon: '🏟️', roles: ADMINS },
  { name: 'areas', label: 'Area', icon: '🗺️', roles: ADMINS },
  { name: 'employees', label: 'Karyawan', icon: '👥', roles: ['admin', 'head_office', 'manager_unit'] },
  { name: 'operational', label: 'Operasional', icon: '💰', roles: ['admin', 'head_office', 'manager_unit', 'admin_unit'] },
  { name: 'procurement', label: 'Procurement', icon: '🛒', roles: ['admin', 'head_office', 'manager_unit', 'admin_unit'] },
  { name: 'payroll', label: 'Payroll', icon: '🧾', roles: ['admin', 'head_office', 'manager_unit'] },
  { name: 'treasury', label: 'Kas & Bank', icon: '🏦', roles: ADMINS },
  { name: 'products', label: 'Produk', icon: '📦', roles: ADMINS },
  { name: 'promos', label: 'Promo', icon: '🎉', roles: ADMINS },
  { name: 'facilities', label: 'Lapangan', icon: '⚽', roles: ADMINS },
  { name: 'bookings', label: 'Booking', icon: '📅', roles: ADMINS },
  { name: 'reports', label: 'Laporan', icon: '📈', roles: ADMINS },
  { name: 'financial', label: 'Laporan Bisnis', icon: '💹', roles: ['admin', 'head_office', 'manager_unit'] },
  { name: 'management-report', label: 'Laporan Manajemen', icon: '🔐', roles: ['admin', 'head_office'] },
  { name: 'setup', label: 'Setup Kasir', icon: '⚙️', roles: ADMINS },
  { name: 'permissions', label: 'Hak Akses', icon: '🔑', roles: ['admin'] },
]
const nav = computed(() => allNav.filter((n) => n.roles.includes(auth.user?.role)))
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
      <nav class="p-4 space-y-1">
        <RouterLink
          v-for="item in nav"
          :key="item.name"
          :to="{ name: item.name }"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-brand-100 hover:bg-white/10 transition"
          active-class="bg-white/15 text-white font-medium"
          @click="sidebarOpen = false"
        >
          <span>{{ item.icon }}</span>{{ item.label }}
        </RouterLink>
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
  </div>
</template>
