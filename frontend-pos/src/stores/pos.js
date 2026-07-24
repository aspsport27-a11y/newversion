import { defineStore } from 'pinia'
import client from '../api/client'

export const usePosStore = defineStore('pos', {
  state: () => ({
    token: localStorage.getItem('pos_token') || null,
    cashier: JSON.parse(localStorage.getItem('pos_cashier') || 'null'),
    terminal: JSON.parse(localStorage.getItem('pos_terminal') || 'null'),
    openShift: null,
    venue: null,
    bookingEnabled: true, // false = mode tiketing (venue tanpa lapangan, mis. waterpark)
    qrisDynamic: false, // true = QR otomatis via BRIAPI; false = QRIS manual (upload bukti)
    products: [],
    facilities: [],
    holidays: [], // tanggal libur nasional (ISO) — utk tarif booking 'holiday'
    stations: [],
    addons: [],
    cart: [], // {uid, item_type, name, unit_price, quantity, ...}
    discount: 0,
    customerName: '',
    customerPhone: '',
  }),
  getters: {
    isAuthenticated: (s) => !!s.token,
    cartCount: (s) => s.cart.reduce((n, i) => n + i.quantity, 0),
    tickets: (s) => s.products.filter((p) => p.is_ticket),
    fnbProducts: (s) => s.products.filter((p) => !p.is_ticket),
    hasStations: (s) => s.stations.length > 0,
    // total per baris, memperhitungkan promo BELI-X-GRATIS-Y
    lineTotal: () => (i) => {
      const promo = i.promo
      let paid = i.quantity
      if (promo && promo.type === 'bogo' && promo.buy_qty && promo.get_qty) {
        const group = promo.buy_qty + promo.get_qty
        const free = Math.floor(i.quantity / group) * promo.get_qty
        paid = i.quantity - free
      }
      return i.unit_price * paid
    },
    subtotal() {
      return this.cart.reduce((s, i) => s + this.lineTotal(i), 0)
    },
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
      this.venue = data.venue
      this.bookingEnabled = data.booking_enabled
      this.qrisDynamic = data.qris_dynamic
      this.openShift = data.open_shift
    },
    async fetchProducts() {
      const { data } = await client.get('/products')
      this.products = data.products
    },
    async fetchFacilities() {
      const { data } = await client.get('/facilities')
      this.facilities = data.facilities
      this.holidays = data.holidays || []
      return data.facilities
    },
    async fetchFacilityBookings(facilityId, date) {
      const { data } = await client.get(`/facilities/${facilityId}/bookings`, {
        params: { date },
      })
      return data.bookings
    },
    // --- station gaming (arena esport) ---
    async fetchStations() {
      const { data } = await client.get('/stations')
      this.stations = data.stations
    },
    async fetchAddons() {
      const { data } = await client.get('/addons')
      this.addons = data.addons
    },
    async startStation(id, customerName, bookedMinutes) {
      const { data } = await client.post(`/stations/${id}/start`, {
        customer_name: customerName || null,
        booked_minutes: bookedMinutes,
      })
      await this.fetchStations()
      return data.session
    },
    async topupStation(id, payload) {
      const { data } = await client.post(`/stations/${id}/topup`, payload)
      await this.fetchStations()
      return data.session
    },
    async attachAddon(id, payload) {
      const { data } = await client.post(`/stations/${id}/addons`, payload)
      await this.fetchStations()
      return data.session
    },
    async detachAddon(id, sessionAddonId) {
      const { data } = await client.delete(`/stations/${id}/addons/${sessionAddonId}`)
      await this.fetchStations()
      return data.session
    },
    async fnbStation(id, productId, delta = 1) {
      const { data } = await client.post(`/stations/${id}/fnb`, { product_id: productId, delta })
      await this.fetchStations()
      return data.session
    },
    async stopStation(id, extraItems) {
      const { data } = await client.post(`/stations/${id}/stop`, { extra_items: extraItems || [] })
      await this.fetchStations()
      return data // { session, order }
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
      const found = this.cart.find((i) => i.item_type === 'product' && i.product_id === p.id)
      if (found) found.quantity += 1
      else
        this.cart.push({
          uid: 'p' + p.id,
          item_type: 'product',
          product_id: p.id,
          name: p.name,
          unit_price: p.effective_price ?? p.price, // harga setelah promo price/percent
          promo: p.promo || null, // untuk BOGO di keranjang
          quantity: 1,
          stock_qty: p.stock_qty,
          track_stock: p.track_stock,
        })
    },
    addTicket(p) {
      const found = this.cart.find((i) => i.item_type === 'ticket' && i.product_id === p.id)
      if (found) found.quantity += 1
      else
        this.cart.push({
          uid: 't' + p.id,
          item_type: 'ticket',
          product_id: p.id,
          name: p.name,
          unit_price: p.effective_price ?? p.price, // harga weekday/weekend hari ini
          quantity: 1,
          track_stock: false,
        })
    },
    addBooking(b) {
      // b: {facility_id, name, unit_price(rate), quantity(hours), booking_date, start_time, end_time}
      const uid = `b${b.facility_id}-${b.booking_date}-${b.start_time}`
      if (this.cart.some((i) => i.uid === uid)) return false
      this.cart.push({ uid, item_type: 'booking', product_id: null, ...b })
      return true
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
      this.customerName = ''
      this.customerPhone = ''
    },
    async checkout(method, extra = {}) {
      const payload = {
        discount_amount: Number(this.discount) || 0,
        customer_name: this.customerName || null,
        customer_phone: this.customerPhone || null,
        items: this.cart.map((i) => {
          if (i.item_type === 'booking')
            return {
              item_type: 'booking',
              facility_id: i.facility_id,
              booking_date: i.booking_date,
              start_time: i.start_time,
              end_time: i.end_time,
            }
          if (i.item_type === 'ticket')
            return { item_type: 'ticket', product_id: i.product_id, quantity: i.quantity }
          return { item_type: 'product', product_id: i.product_id, quantity: i.quantity }
        }),
      }
      const { data: created } = await client.post('/orders', payload)
      const { data: paid } = await client.post(`/orders/${created.order.id}/pay`, {
        method,
        amount: extra.amount ?? null,
        reference: extra.reference || null,
        proof_image: extra.proof_image || null,
      })
      return paid // { order, payment }
    },
    async fetchOutstanding() {
      const { data } = await client.get('/orders/outstanding')
      return data.orders
    },
    async createMemberBooking(payload) {
      const { data } = await client.post('/bookings/member', payload)
      return data // { order, per_session, booked_dates, skipped_dates }
    },
    async settle(orderId, method, amount, reference, proofImage) {
      const { data } = await client.post(`/orders/${orderId}/pay`, {
        method,
        amount: amount ?? null,
        reference: reference || null,
        proof_image: proofImage || null,
      })
      return data // { order, payment }
    },
    async cancelOrder(orderId) {
      const { data } = await client.post(`/orders/${orderId}/cancel`)
      return data
    },
    // --- QRIS dinamis (BRIAPI) ---
    // qrisStatus dipanggil berulang (polling) — murni baca DB di server, murah.
    async qrisStatus(paymentId) {
      const { data } = await client.get(`/payments/${paymentId}/qris`)
      return data
    },
    // qrisSync memaksa server bertanya ke BRI — dipakai tombol "Cek status",
    // jangan dipakai untuk polling otomatis (membebani API bank).
    async qrisSync(paymentId) {
      const { data } = await client.post(`/payments/${paymentId}/qris/sync`)
      return data
    },
    logout() {
      this.$reset()
      localStorage.removeItem('pos_token')
      localStorage.removeItem('pos_cashier')
      localStorage.removeItem('pos_terminal')
    },
  },
})
