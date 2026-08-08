<script setup>
import { ref, nextTick } from 'vue'
import client from '../api/client'

const emit = defineEmits(['close'])

const messages = ref([])
const question = ref('')
const busy = ref(false)
const err = ref('')
const scrollEl = ref(null)

// Pertanyaan contoh siap-klik — bantu user yang bingung mau nanya apa.
const SUGGESTIONS = [
  'Apa yang perlu saya cek hari ini?',
  'Ringkas kondisi bisnis sekarang',
  'Venue mana paling ramai bulan ini?',
  'Berapa piutang yang belum tertagih?',
]
function ask(q) {
  question.value = q
  send()
}

async function scrollToBottom() {
  await nextTick()
  if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
}

async function send() {
  const q = question.value.trim()
  if (!q || busy.value) return
  err.value = ''
  messages.value.push({ role: 'user', content: q })
  question.value = ''
  busy.value = true
  scrollToBottom()
  try {
    const { data } = await client.post('/ai/ask', {
      question: q,
      history: messages.value.slice(0, -1),
    })
    messages.value.push({ role: 'assistant', content: data.answer })
  } catch (e) {
    err.value = e?.response?.data?.message || 'Gagal menghubungi AI.'
  } finally {
    busy.value = false
    scrollToBottom()
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" @click.self="emit('close')">
    <div class="bg-white w-full max-w-lg rounded-2xl flex flex-col" style="height: 80vh; max-height: 640px">
      <div class="flex justify-between items-center px-5 py-4 border-b">
        <h3 class="text-lg font-bold text-slate-800">✨ Ask AI</h3>
        <button @click="emit('close')" class="text-slate-400 text-xl">✕</button>
      </div>

      <div ref="scrollEl" class="flex-1 overflow-auto px-5 py-4 space-y-3">
        <div v-if="!messages.length" class="mt-6">
          <p class="text-center text-slate-400 text-sm">
            Tanya apa saja seputar operasional venue atau cara pakai sistem ini.
          </p>
          <p class="text-center text-xs text-slate-400 mt-4 mb-2">Contoh pertanyaan:</p>
          <div class="flex flex-col gap-2 max-w-sm mx-auto">
            <button
              v-for="s in SUGGESTIONS"
              :key="s"
              @click="ask(s)"
              :disabled="busy"
              class="text-left text-sm text-brand-700 bg-brand-50 hover:bg-brand-100 border border-brand-100 rounded-lg px-3 py-2 transition disabled:opacity-50"
            >{{ s }}</button>
          </div>
        </div>
        <div v-for="(m, i) in messages" :key="i" :class="m.role === 'user' ? 'flex justify-end' : 'flex justify-start'">
          <div
            class="max-w-[85%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap"
            :class="m.role === 'user' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-700'"
          >{{ m.content }}</div>
        </div>
        <div v-if="busy" class="flex justify-start">
          <div class="max-w-[85%] rounded-xl px-3 py-2 text-sm bg-slate-100 text-slate-400">Berpikir…</div>
        </div>
      </div>

      <p v-if="err" class="text-sm text-red-600 bg-red-50 px-5 py-2">{{ err }}</p>

      <div class="p-4 border-t flex gap-2">
        <input
          v-model="question"
          type="text"
          placeholder="Tulis pertanyaan…"
          :disabled="busy"
          @keyup.enter="send"
          class="flex-1 rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500 disabled:opacity-60"
        />
        <button
          @click="send"
          :disabled="busy || !question.trim()"
          class="px-4 py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium disabled:opacity-40"
        >Kirim</button>
      </div>
    </div>
  </div>
</template>
