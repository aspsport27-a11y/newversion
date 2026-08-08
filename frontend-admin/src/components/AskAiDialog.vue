<script setup>
import { ref, nextTick, onMounted, computed } from 'vue'
import client from '../api/client'

const emit = defineEmits(['close'])

const messages = ref([])
const question = ref('')
const busy = ref(false)
const err = ref('')
const scrollEl = ref(null)
const modelLabel = ref('AI')

// Sapaan menyesuaikan waktu (seperti komposer Claude)
const greeting = computed(() => {
  const h = new Date().getHours()
  const t = h < 11 ? 'pagi' : h < 15 ? 'siang' : h < 18 ? 'sore' : 'malam'
  return `Mau tanya apa ${t} ini?`
})

// Pertanyaan contoh siap-klik — bantu user yang bingung mau nanya apa.
const SUGGESTIONS = [
  'Apa yang perlu saya cek hari ini?',
  'Ringkas kondisi bisnis sekarang',
  'Venue mana paling ramai bulan ini?',
  'Berapa piutang yang belum tertagih?',
]

onMounted(async () => {
  try {
    const { data } = await client.get('/ai/info')
    if (data.model_label) modelLabel.value = data.model_label
  } catch (_) { /* diam saja, badge tetap default */ }
})

async function scrollToBottom() {
  await nextTick()
  if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
}

function ask(q) {
  question.value = q
  send()
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
  <div class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" @click.self="emit('close')">
    <div
      class="w-full max-w-xl rounded-3xl flex flex-col overflow-hidden shadow-xl"
      style="height: 82vh; max-height: 660px; background: #faf9f5"
    >
      <!-- header minimalis -->
      <div class="flex justify-end px-4 pt-4">
        <button @click="emit('close')" class="text-slate-400 hover:text-slate-600 text-xl leading-none">✕</button>
      </div>

      <!-- area isi -->
      <div ref="scrollEl" class="flex-1 overflow-auto px-6">
        <!-- EMPTY STATE: sapaan besar + komposer + contoh -->
        <div v-if="!messages.length" class="h-full flex flex-col items-center justify-center text-center">
          <div class="flex items-center gap-3 mb-7">
            <svg width="30" height="30" viewBox="0 0 24 24" stroke="#d97757" stroke-width="2" stroke-linecap="round">
              <line x1="12" y1="2.5" x2="12" y2="21.5" /><line x1="2.5" y1="12" x2="21.5" y2="12" />
              <line x1="5.2" y1="5.2" x2="18.8" y2="18.8" /><line x1="18.8" y1="5.2" x2="5.2" y2="18.8" />
            </svg>
            <h3 class="text-2xl sm:text-3xl text-slate-700" style="font-family: Georgia, 'Times New Roman', serif">
              {{ greeting }}
            </h3>
          </div>

          <div class="w-full max-w-md">
            <div class="rounded-2xl border border-[#e6e3d8] bg-white shadow-sm px-4 pt-3 pb-2 text-left">
              <input
                v-model="question"
                type="text"
                placeholder="Apa yang bisa saya bantu hari ini?"
                :disabled="busy"
                @keyup.enter="send"
                class="w-full bg-transparent outline-none text-sm text-slate-700 placeholder:text-slate-400 disabled:opacity-60"
              />
              <div class="flex items-center justify-between mt-2.5">
                <span class="text-xs text-slate-400 flex items-center gap-1">
                  <span style="color: #d97757">✳</span> {{ modelLabel }}
                </span>
                <button
                  @click="send"
                  :disabled="busy || !question.trim()"
                  class="h-8 w-8 rounded-full bg-brand-600 hover:bg-brand-700 text-white flex items-center justify-center disabled:opacity-40 transition"
                  aria-label="Kirim"
                >↑</button>
              </div>
            </div>

            <div class="flex flex-wrap justify-center gap-2 mt-5">
              <button
                v-for="s in SUGGESTIONS"
                :key="s"
                @click="ask(s)"
                :disabled="busy"
                class="text-xs text-slate-600 bg-white hover:bg-slate-50 border border-[#e6e3d8] rounded-full px-3 py-1.5 transition disabled:opacity-50"
              >{{ s }}</button>
            </div>
          </div>
        </div>

        <!-- PERCAKAPAN -->
        <div v-else class="py-4 space-y-3">
          <div v-for="(m, i) in messages" :key="i" :class="m.role === 'user' ? 'flex justify-end' : 'flex justify-start'">
            <div
              class="max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm whitespace-pre-wrap"
              :class="m.role === 'user' ? 'bg-brand-600 text-white' : 'bg-white border border-[#ece9df] text-slate-700'"
            >{{ m.content }}</div>
          </div>
          <div v-if="busy" class="flex justify-start">
            <div class="rounded-2xl px-3.5 py-2.5 text-sm bg-white border border-[#ece9df] text-slate-400">Berpikir…</div>
          </div>
        </div>
      </div>

      <p v-if="err" class="text-sm text-red-600 bg-red-50 mx-6 rounded-lg px-3 py-2">{{ err }}</p>

      <!-- KOMPOSER BAWAH (saat sudah ada percakapan) -->
      <div v-if="messages.length" class="p-4">
        <div class="rounded-2xl border border-[#e6e3d8] bg-white shadow-sm px-4 pt-3 pb-2">
          <input
            v-model="question"
            type="text"
            placeholder="Tulis pertanyaan lanjutan…"
            :disabled="busy"
            @keyup.enter="send"
            class="w-full bg-transparent outline-none text-sm text-slate-700 placeholder:text-slate-400 disabled:opacity-60"
          />
          <div class="flex items-center justify-between mt-2.5">
            <span class="text-xs text-slate-400 flex items-center gap-1">
              <span style="color: #d97757">✳</span> {{ modelLabel }}
            </span>
            <button
              @click="send"
              :disabled="busy || !question.trim()"
              class="h-8 w-8 rounded-full bg-brand-600 hover:bg-brand-700 text-white flex items-center justify-center disabled:opacity-40 transition"
              aria-label="Kirim"
            >↑</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
