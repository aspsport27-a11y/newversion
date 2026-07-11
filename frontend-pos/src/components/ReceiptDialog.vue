<script setup>
const props = defineProps({ order: Object, payment: Object, terminal: Object })
const emit = defineEmits(['close'])

function rupiah(n) {
  return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
}
function print() {
  window.print()
}
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4">
    <div class="bg-white w-full max-w-xs rounded-2xl overflow-hidden">
      <!-- struk -->
      <div id="receipt" class="p-5 text-sm">
        <div class="text-center mb-2">
          <img src="/asp-logo.png" alt="ASP Sports" class="h-8 mx-auto mb-1" />
          <p class="text-xs">{{ terminal?.name }}</p>
        </div>
        <div class="border-t border-dashed border-slate-300 my-2"></div>
        <div class="flex justify-between text-xs">
          <span>{{ order.order_number }}</span>
          <span>{{ new Date(order.created_at).toLocaleString('id-ID') }}</span>
        </div>
        <div class="border-t border-dashed border-slate-300 my-2"></div>
        <div v-for="it in order.items" :key="it.id" class="mb-1">
          <div class="flex justify-between">
            <span>{{ it.name }}</span>
            <span>{{ rupiah(it.line_total) }}</span>
          </div>
          <div class="text-xs text-slate-500">{{ it.quantity }} x {{ rupiah(it.unit_price) }}</div>
        </div>
        <div class="border-t border-dashed border-slate-300 my-2"></div>
        <div class="flex justify-between"><span>Subtotal</span><span>{{ rupiah(order.subtotal) }}</span></div>
        <div v-if="order.discount_amount > 0" class="flex justify-between"><span>Diskon</span><span>-{{ rupiah(order.discount_amount) }}</span></div>
        <div class="flex justify-between font-bold text-base"><span>TOTAL</span><span>{{ rupiah(order.total_amount) }}</span></div>
        <div class="flex justify-between text-xs mt-1">
          <span>Dibayar ({{ payment.method.toUpperCase() }})</span>
          <span>{{ rupiah(payment.amount) }}</span>
        </div>
        <div v-if="order.amount_due > 0" class="flex justify-between text-xs">
          <span>Sisa</span><span>{{ rupiah(order.amount_due) }}</span>
        </div>
        <div class="flex justify-between text-xs font-bold mt-0.5">
          <span>STATUS</span>
          <span>{{ order.status === 'paid' ? 'LUNAS' : (order.status === 'partial' ? 'DP / BELUM LUNAS' : payment.status.toUpperCase()) }}</span>
        </div>
        <div class="border-t border-dashed border-slate-300 my-2"></div>
        <p class="text-center text-xs">Terima kasih 🙏</p>
      </div>

      <div class="no-print p-4 border-t flex gap-2">
        <button @click="print" class="flex-1 py-2.5 rounded-lg bg-brand-600 text-white font-medium">🖨️ Cetak</button>
        <button @click="emit('close')" class="flex-1 py-2.5 rounded-lg bg-slate-100 text-slate-600 font-medium">Selesai</button>
      </div>
    </div>
  </div>
</template>
