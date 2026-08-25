// Perhitungan harga booking sadar-hari + carry-forward — cermin
// facility_rate_for_hour() di backend (app/pos/models.py). Dipakai preview POS.

export function expandRange(startStr, endStr) {
  const sh = parseInt(startStr.slice(0, 2))
  let eh = parseInt(endStr.slice(0, 2))
  if (endStr === '00:00' || eh <= sh) eh += 24
  return [sh, eh]
}

// kategori hari dari tanggal ISO (holiday > kamis > sabtu/minggu > weekday)
export function dayTypeFor(iso, holidays = []) {
  if (!iso) return 'weekday'
  if ((holidays || []).includes(iso)) return 'holiday'
  const [y, m, d] = iso.split('-').map(Number)
  const wd = new Date(y, m - 1, d).getDay() // 0=Minggu, 4=Kamis, 5=Jumat, 6=Sabtu
  if (wd === 4) return 'thursday'
  if (wd === 5) return 'friday'
  if (wd === 6) return 'saturday'
  if (wd === 0) return 'sunday'
  return 'weekday'
}

export function rateForHour(f, h, dt) {
  // 'thursday'/'friday' = override khusus (Kamis/Jumat): hanya jam yg TEPAT
  // tercakup band hari itu; jam lain pakai tarif weekday (tanpa carry-forward).
  if (dt === 'thursday' || dt === 'friday') {
    for (const r of f.rate_rules || []) {
      if ((r.day_type || 'weekday') !== dt) continue
      const [sh, eh] = expandRange(r.start_time, r.end_time)
      const hh = h >= sh ? h : h + 24
      if (hh >= sh && hh < eh) return Number(r.hourly_rate)
    }
    return rateForHour(f, h, 'weekday')
  }
  const rules = (f.rate_rules || []).filter((r) => (r.day_type || 'weekday') === dt)
  if (!rules.length) {
    const fb = { holiday: 'sunday', saturday: 'weekday', sunday: 'weekday' }[dt]
    if (fb) return rateForHour(f, h, fb)
  }
  let carry = null
  for (const r of rules) {
    const [sh, eh] = expandRange(r.start_time, r.end_time)
    const hh = h >= sh ? h : h + 24
    if (hh >= sh && hh < eh) return Number(r.hourly_rate)
    if (h >= sh && (carry === null || sh > carry[0])) carry = [sh, Number(r.hourly_rate)]
  }
  if (carry !== null) return carry[1]
  return Number(f.hourly_rate || 0)
}

// total harga dari jam startH s/d endH (exclusive) pada kategori hari dt
export function bookingPrice(f, startH, endH, dt) {
  if (!f || startH == null || endH == null || endH <= startH) return 0
  let t = 0
  for (let h = startH; h < endH; h++) t += rateForHour(f, h % 24, dt)
  return t
}
