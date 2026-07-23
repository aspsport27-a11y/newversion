import { parseUTC } from './datetime'

// Kalkulasi jam & harga sesi Station Gaming — dipakai bareng oleh grid
// station (PosView) & dialog sesi (StationSessionDialog) spy konsisten.
// MODEL PAKET TETAP: sewa station = FIX jam dipesan (booked_minutes) x tarif,
// bukan per menit terpakai. Jam di layar hitung MUNDUR dari waktu yg dibeli
// (paket awal + semua Tambah Waktu). Merah/negatif = lewat waktu.
// Sesi lama (booked_minutes 0, sebelum fitur ini) fallback ke perhitungan
// elapsed lama. Harus SAMA PERSIS dgn GameSession di backend (sumber harga
// final saat stop) — ini cuma preview live.
export function stationClock(session, nowMs, hourlyRate) {
  if (!session) return null
  const started = parseUTC(session.started_at).getTime()
  const elapsedSeconds = Math.max(0, Math.floor((nowMs - started) / 1000))
  const elapsedMinutes = Math.floor(elapsedSeconds / 60)

  const bookedMinutes = Number(session.booked_minutes || 0)
  const isLegacy = bookedMinutes <= 0
  const topupMinutes = (session.topups || []).reduce((s, t) => s + Number(t.duration_minutes || 0), 0)
  // waktu yg dibeli (paket + tambah waktu); sesi lama pakai topup saja (perilaku lama)
  const allocatedMinutes = isLegacy ? topupMinutes : bookedMinutes + topupMinutes

  const isCountdown = allocatedMinutes > 0
  const remainingSeconds = allocatedMinutes * 60 - elapsedSeconds
  const isOvertime = isCountdown && remainingSeconds < 0

  const clockSeconds = Math.abs(isCountdown ? remainingSeconds : elapsedSeconds)
  const h = String(Math.floor(clockSeconds / 3600)).padStart(2, '0')
  const m = String(Math.floor((clockSeconds % 3600) / 60)).padStart(2, '0')
  const sec = String(clockSeconds % 60).padStart(2, '0')
  const clockLabel = (isOvertime ? '-' : '') + `${h}:${m}:${sec}`

  // sewa station: FIX dari paket (booked); sesi lama fallback elapsed
  const baseMinutes = isLegacy ? elapsedMinutes : bookedMinutes
  const timeCharge = Math.round((baseMinutes / 60) * Number(hourlyRate) * 100) / 100
  const topupCharge = (session.topups || []).reduce((s, t) => s + Number(t.total_amount), 0)
  // add-on ikut waktu yg dibayar (fix); sesi lama fallback elapsed
  const billableMinutes = isLegacy ? elapsedMinutes : allocatedMinutes
  const addonCharge = (session.addons || []).reduce(
    (s, a) => s + (billableMinutes / 60) * Number(a.rate_per_hour) * a.quantity, 0,
  )

  return {
    elapsedSeconds, elapsedMinutes, allocatedMinutes, billableMinutes, isCountdown, remainingSeconds, isOvertime,
    clockLabel, timeCharge, topupCharge, addonCharge,
    runningTotal: timeCharge + topupCharge + addonCharge,
  }
}

// Bunyi alarm sederhana (beep, tanpa perlu file audio) — dipakai saat waktu
// sesi station habis. Web Audio API dibuat on-demand tiap panggil supaya
// tak nyangkut kalau tab sempat idle lama.
export function playAlarmBeep() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext
    const ctx = new Ctx()
    const beep = (start, freq) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'square'
      osc.frequency.value = freq
      gain.gain.setValueAtTime(0.2, ctx.currentTime + start)
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start(ctx.currentTime + start)
      osc.stop(ctx.currentTime + start + 0.25)
    }
    beep(0, 880)
    beep(0.3, 880)
    beep(0.6, 880)
    setTimeout(() => ctx.close(), 1200)
  } catch (_) { /* browser tak dukung Web Audio — abaikan, jangan sampai error ganggu POS */ }
}
