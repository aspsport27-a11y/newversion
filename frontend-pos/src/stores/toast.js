import { defineStore } from 'pinia'

let nextId = 1

// Notifikasi kecil non-blocking (beda dari alert() yg mengharuskan klik OK).
// Dipakai di seluruh POS lewat satu <ToastContainer /> global di App.vue —
// jangan bikin toast lokal per-view lagi.
export const useToastStore = defineStore('toast', {
  state: () => ({ items: [] }),
  actions: {
    show(message, type = 'success', duration = 2500) {
      const id = nextId++
      this.items.push({ id, message, type })
      setTimeout(() => this.dismiss(id), duration)
      return id
    },
    dismiss(id) {
      this.items = this.items.filter((i) => i.id !== id)
    },
  },
})
