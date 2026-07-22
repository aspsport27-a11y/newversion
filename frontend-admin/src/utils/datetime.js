// Backend kirim datetime dlm UTC tanpa info timezone (mis. "2026-07-22T13:45:00")
// — kalau langsung di-`new Date()`, browser salah baca sbg waktu lokal device,
// bukan UTC, jadi jam yg tampil meleset sebesar offset zona waktu (mis. -8 jam
// utk WITA). Tambahkan 'Z' dulu spy dikonversi dgn benar ke zona waktu lokal.
export function parseUTC(s) {
  if (!s) return null
  const hasTz = /[Zz]|[+-]\d{2}:?\d{2}$/.test(s)
  return new Date(hasTz ? s : s + 'Z')
}
