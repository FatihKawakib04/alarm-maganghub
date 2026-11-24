# alarm-maganghub

Pengingat laporan harian MagangHub lewat email. Cron jalan Senin sampai Jumat pukul 20:00 WIB,
mengirim satu email berisi pengingat mengisi kehadiran dan laporan aktivitas sebelum batas
pengisian **23.59 WIB** (sesuai dashboard monev peserta).

Tampilan email dibangun pakai **MJML** (framework email), bukan HTML tulis tangan.
Sumber desain ada di `src/reminder.mjml`, hasil build ada di `dist/reminder.html`, dan
`reminder.py` cuma mengisi placeholder tanggal/jam lalu mengirim lewat Resend (atau SMTP Gmail).

## Cara kerja

```
cron (Sen-Jum 20:00 WIB)
  └─ scripts/maganghub-reminder.sh
       └─ reminder.py
            ├─ baca dist/reminder.html  → isi {{TANGGAL}} {{JAM}} {{SISA}} {{SITE}}
            ├─ kirim email (Resend API, fallback SMTP Gmail)
            └─ kalau email gagal → stdout berisi pengingat, cron meneruskannya ke Telegram
```

Email yang sukses tidak menghasilkan output apa pun, jadi cron tidak spam chat.
Email yang gagal tetap menyampaikan pengingatnya lewat jalur cadangan.

## Struktur

```
src/reminder.mjml      sumber desain email (MJML)
dist/reminder.html     hasil build, dibaca reminder.py
dist/preview*.png      screenshot preview (dokumentasi tampilan)
reminder.py            render template + kirim email (stdlib saja)
package.json           dependency build (mjml)
```

## Setup

Butuh Python 3 (tanpa dependency tambahan) dan Node.js hanya kalau mau ubah desain.

```bash
git clone https://github.com/FatihKawakib04/alarm-maganghub.git
cd alarm-maganghub
npm install          # hanya untuk build template
```

Konfigurasi dibaca dari environment atau `.env` (default `/root/.hermes/.env`):

| Variabel | Wajib | Default | Keterangan |
|---|---|---|---|
| `RESEND_API_KEY` | salah satu | - | kirim lewat Resend |
| `GMAIL_USER` + `GMAIL_APP_PASSWORD` | salah satu | - | kirim lewat SMTP Gmail (menang kalau diisi) |
| `MAGANGHUB_TO` | tidak | `maganghub@satgas.ai.id` | satu atau beberapa alamat, pisah koma |
| `MAGANGHUB_FROM` | tidak | `alarm@satgas.ai.id` | domain pengirim harus terverifikasi di Resend |

Jadwal cron:

```cron
0 13 * * 1-5  /root/.hermes/scripts/maganghub-reminder.sh
```

## Perintah

```bash
python3 reminder.py --check     # cek konfigurasi, tidak mengirim
python3 reminder.py --preview   # tulis HTML hasil render ke dist/preview.html
python3 reminder.py --test      # kirim email percobaan sekarang
```

## Ubah desain

```bash
npm run build     # src/reminder.mjml -> dist/reminder.html
```

Aturan mainnya:

- **Jangan** edit `dist/reminder.html` langsung, file itu hasil generate. Edit `src/reminder.mjml`.
- Placeholder yang dikenali `reminder.py`: `{{TANGGAL}}`, `{{JAM}}`, `{{SISA}}`, `{{SITE}}`,
  `{{SITE_HOST}}`. Kalau menambah placeholder baru, tambahkan juga pasangannya di `render_html()`.
  `{{SISA}}` dihitung dari waktu kirim ke batas 23.59 WIB, jadi angkanya tidak pernah basi.
- Tema mengikuti brand MagangHub: biru `#0b60ea`, navy `#0f1729`, amber `#f4a825`
  (dipakai untuk chip batas isi), background `#f4f6fa`.
- Layout sudah diuji di lebar 640px dan 390px (chip tanggal/batas isi menumpuk di HP),
  plus dark mode (`prefers-color-scheme: dark`).
- Tautan CTA mengarah ke `https://monev.maganghub.kemnaker.go.id/dashboard`.
- `dist/reminder.html` ikut di-commit supaya pengingat tetap jalan walau Node tidak terpasang.

## Catatan

- Tidak ada kredensial di repo ini. Semua API key ada di `.env` di server.
- Kalau `dist/reminder.html` hilang, `reminder.py` pakai fallback HTML sederhana supaya
  pengingat tetap terkirim. Jalankan `npm run build` untuk mengembalikan tampilan penuh.
