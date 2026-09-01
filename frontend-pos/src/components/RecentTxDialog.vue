<script setup>
import { ref, onMounted, computed } from 'vue'
import { usePosStore } from '../stores/pos'
import { parseUTC } from '../utils/datetime'

const pos = usePosStore()
const emit = defineEmits(['close', 'changed'])

const orders = ref([])
const loading = ref(true)
const busy = ref(false)
const err = ref('')
const search = ref('')

function rupiah(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID') }
function fmtTime(s) { return s ? parseUTC(s).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) : '' }
const statusMap = { paid: ['Lunas', 'bg-emerald-100 text-emerald-700'], open: ['Belum bayar', 'bg-amber-100 text-amber-700'], partial: ['DP', 'bg-amber-100 text-amber-700'], void: ['Dibatalkan', 'bg-red-100 text-red-500'] }

async function load() {
  loading.value = true
  try { orders.value = await pos.fetchRecentOrders() }
  catch (e) { err.value = e?.response?.data?.message || 'Gagal memuat.' }
  finally { loading.value = false }
}
onMounted(load)

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return orders.value
  return orders.value.filter((o) => (o.order_number || '').toLowerCase().includes(q) || (o.customer_name || '').toLowerCase().includes(q))
})

// ---- edit item (koreksi salah entry tanpa batal) ----
const EDITABLE = ['product', 'ticket']
const editingId = ref(null)
const editItems = ref([])
const editLocked = ref([])
const editErr = ref('')
const savingEdit = ref(false)
function openEdit(o) {
  editingId.value = o.id
  editErr.value = ''
  editItems.value = (o.items || []).filter((i) => EDITABLE.includes(i.item_type))
    .map((i) => ({ item_type: i.item_type, product_id: i.product_id || null, name: i.name, quantity: Number(i.quantity), unit_price: Number(i.unit_price) }))
  editLocked.value = (o.items || []).filter((i) => !EDITABLE.includes(i.item_type))
}
function addEditLine() { editItems.value.push({ item_type: 'product', product_id: null, name: '', quantity: 1, unit_price: null }) }
function rmEditLine(i) { editItems.value.splice(i, 1) }
const editTotal = computed(() =>
  editItems.value.reduce((t, i) => t + (Number(i.quantity) || 0) * (Number(i.unit_price) || 0), 0) +
  editLocked.value.reduce((t, i) => t + (Number(i.line_total) || 0), 0))
async function saveEdit(o) {
  const items = editItems.value.filter((i) => i.name?.trim() && Number(i.quantity) > 0)
    .map((i) => ({ item_type: i.item_type || 'product', product_id: i.product_id || null, name: i.name.trim(), quantity: Number(i.quantity), unit_price: Number(i.unit_price) || 0 }))
  savingEdit.value = true; editErr.value = ''
  try {
    await pos.editOrderItems(o.id, items)
    editingId.value = null
    await load(); emit('changed')
  } catch (e) { editErr.value = e?.response?.data?.message || 'Gagal menyimpan.' }
  finally { savingEdit.value = false }
}

async function cancel(o) {
  if (o.status === 'void') return
  if (!window.confirm(`Batalkan transaksi ${o.order_number}${o.customer_name ? ' — ' + o.customer_name : ''} (${rupiah(o.total_amount)})?\n\nStok dikembalikan & uang dikeluarkan dari shift ini. Lanjutkan?`)) return
  busy.value = true; err.value = ''
  try {
    await pos.cancelOrder(o.id)
    await load()
    emit('changed')
  } catch (e) { err.value = e?.response?.data?.message || 'Gagal membatalkan.' }
  finally { busy.value = false }
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 max-h-[92vh] overflow-auto">
      <div class="flex justify-between items-center mb-1">
        <h3 class="text-lg font-bold text-slate-800">🧾 Transaksi Shift Ini</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>
      <p class="text-xs text-slate-400 mb-3">Batalkan transaksi yang salah entry (hanya shift yang sedang berjalan). Setelah batal, input ulang dengan benar.</p>

      <input v-if="orders.length" v-model="search" type="text" placeholder="🔍 Cari kode / nama…"
        class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500 mb-3" />

      <p v-if="loading" class="text-center text-slate-400 py-6">Memuat…</p>
      <p v-else-if="!orders.length" class="text-center text-slate-400 py-6">Belum ada transaksi di shift ini.</p>
      <p v-else-if="!filtered.length" class="text-center text-slate-400 py-6">Tidak ada yang cocok.</p>

      <div v-else class="space-y-2">
        <div v-for="o in filtered" :key="o.id" class="border rounded-xl p-3" :class="o.status === 'void' ? 'opacity-60' : ''">
          <div class="flex justify-between items-start">
            <div class="min-w-0">
              <p class="font-medium text-slate-800 truncate">{{ o.customer_name || 'Umum' }}
                <span class="text-xs rounded-full px-2 py-0.5 ml-1" :class="statusMap[o.status]?.[1]">{{ statusMap[o.status]?.[0] || o.status }}</span>
              </p>
              <p class="text-xs text-slate-400 font-mono">{{ o.order_number }} · {{ fmtTime(o.created_at) }}</p>
            </div>
            <div class="text-right pl-2">
              <p class="font-bold text-slate-800 whitespace-nowrap">{{ rupiah(o.total_amount) }}</p>
            </div>
          </div>

          <!-- ringkasan item (mode lihat) -->
          <template v-if="editingId !== o.id">
            <p v-for="it in (o.items || []).slice(0, 5)" :key="it.id" class="text-xs text-slate-500 truncate">• {{ it.name }} <span class="text-slate-400">×{{ it.quantity }}</span></p>
            <p v-if="(o.items || []).length > 5" class="text-xs text-slate-400">+{{ o.items.length - 5 }} item lain…</p>
            <div v-if="o.status !== 'void'" class="flex gap-2 mt-2">
              <button @click="openEdit(o)" :disabled="busy" class="flex-1 py-2 rounded-lg bg-blue-50 hover:bg-blue-100 text-blue-700 text-sm font-medium disabled:opacity-50">✏️ Edit Item</button>
              <button @click="cancel(o)" :disabled="busy" class="flex-1 py-2 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 text-sm font-medium disabled:opacity-50">Batalkan</button>
            </div>
          </template>

          <!-- editor item (mode edit) -->
          <div v-else class="mt-2 space-y-1.5">
            <p class="text-xs text-slate-500">Ubah nama/qty/harga item, lalu Simpan. Kas & total ikut menyesuaikan.</p>
            <div v-for="lk in editLocked" :key="'lk'+lk.id" class="flex items-center gap-2 text-xs text-slate-500">
              <span class="flex-1 truncate">🔒 {{ lk.name }}</span><span>{{ lk.quantity }}×</span><span>{{ rupiah(lk.line_total) }}</span>
            </div>
            <div v-for="(it, i) in editItems" :key="i" class="flex items-center gap-1.5">
              <input v-model="it.name" placeholder="Nama item" class="flex-1 min-w-0 rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none" />
              <input v-model.number="it.quantity" type="number" min="1" class="w-12 rounded-lg border border-slate-300 px-1 py-1.5 text-sm text-right outline-none" />
              <input v-model.number="it.unit_price" type="number" placeholder="Harga" class="w-24 rounded-lg border border-slate-300 px-2 py-1.5 text-sm text-right outline-none" />
              <button @click="rmEditLine(i)" class="text-red-400 px-1">✕</button>
            </div>
            <button @click="addEditLine" class="text-brand-600 text-xs">+ item</button>
            <div class="flex justify-between text-sm border-t pt-1.5"><span class="text-slate-500">Total baru</span><span class="font-semibold text-brand-700">{{ rupiah(editTotal) }}</span></div>
            <p v-if="editErr" class="text-xs text-red-600">{{ editErr }}</p>
            <div class="flex gap-2">
              <button @click="editingId = null" class="flex-1 py-2 rounded-lg bg-slate-100 text-slate-600 text-sm">Batal</button>
              <button @click="saveEdit(o)" :disabled="savingEdit" class="flex-1 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium disabled:opacity-50">{{ savingEdit ? 'Menyimpan…' : 'Simpan' }}</button>
            </div>
          </div>
        </div>
      </div>

      <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mt-3">{{ err }}</p>
    </div>
  </div>
</template>
