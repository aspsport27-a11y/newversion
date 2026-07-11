import { defineStore } from 'pinia'
import client from '../api/client'

export const usePosStore = defineStore('pos', {
  state: () => ({
    token: localStorage.getItem('pos_token') || null,
    cashier: JSON.parse(localStorage.getItem('pos_cashier') || 'null'),
    terminal: JSON.parse(localStorage.getItem('pos_terminal') || 'null'),
    openShift: null,
    products: [],
    cart: [], // {product_id, name, unit_price, quantity, item_type}
    discount: 0,
  }),
  getters: {
    isAuthenticated: (s) => !!s.token,
    cartCount: (s) => s.cart.reduce((n, i) => n + i.quantity, 0),
    subtotal: (s) => s.cart.reduce((sum, i) => sum + i.unit_price * i.quantity, 0),
    total() {
      return Math.max(0, this.subtotal - (Number(this.discount) || 0))
    },
  },
  actions: {
    async login(terminalCode, username, pin) {
      const { data } = await client.post('/auth/login', {
        terminal_code: terminalCode,
        username,
        pin,
      })
      this.token = data.access_token
      this.cashier = data.cashier
      this.terminal = data.terminal
      localStorage.setItem('pos_token', data.access_token)
      localStorage.setItem('pos_cashier', JSON.stringify(data.cashier))
      localStorage.setItem('pos_terminal', JSON.stringify(data.terminal))
    },
    async fetchMe() {
      const { data } = await client.get('/me')
      this.terminal = data.terminal
      this.openShift = data.open_shift
    },
    async fetchProducts() {
      const { data } = await client.get('/products')
      this.products = data.products
    },
    async doOpenShift(openingCash) {
      const { data } = await client.post('/shifts/open', { opening_cash: openingCash })
      this.openShift = data.shift
    },
    async doCloseShift(countedCash, depositAmount, notes) {
      const { data } = await client.post('/shifts/close', {
        counted_cash: countedCash,
        deposit_amount: depositAmount,
        notes,
      })
      this.openShift = null
      return data.shift
    },
    // --- keranjang ---
    addProduct(p) {
      const found = this.cart.find((i) => i.product_id === p.id)
      if (found) found.quantity += 1
      else
        this.cart.push({
          product_id: p.id,
          name: p.name,
          unit_price: p.price,
          quantity: 1,
          item_type: 'product',
          stock_qty: p.stock_qty,
          track_stock: p.track_stock,
        })
    },
    incQty(item) {
      item.quantity += 1
    },
    decQty(item) {
      item.quantity -= 1
      if (item.quantity <= 0) this.removeItem(item)
    },
    removeItem(item) {
      this.cart = this.cart.filter((i) => i !== item)
    },
    clearCart() {
      this.cart = []
      this.discount = 0
    },
    async checkout(method, extra = {}) {
      const payload = {
        discount_amount: Number(this.discount) || 0,
        customer_name: extra.customer_name || null,
        items: this.cart.map((i) => ({
          item_type: 'product',
          product_id: i.product_id,
          quantity: i.quantity,
        })),
      }
      const { data: created } = await client.post('/orders', payload)
      const { data: paid } = await client.post(`/orders/${created.order.id}/pay`, {
        method,
        reference: extra.reference || null,
      })
      return paid // { order, payment }
    },
    logout() {
      this.$reset()
      localStorage.removeItem('pos_token')
      localStorage.removeItem('pos_cashier')
      localStorage.removeItem('pos_terminal')
    },
  },
})
