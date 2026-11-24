# alarm-maganghub

Pengingat absen MagangHub lewat email. Cron jalan Senin sampai Jumat pukul 20:00 WIB,
mengirim satu email berisi pengingat mengisi Laporan Aktivitas Magang.

Tampilan email dibangun pakai **MJML** (framework email), bukan HTML tulis tangan.
Sumber desain ada di `src/reminder.mjml`, hasil build ada di `dist/reminder.html`, dan
`reminder.py` cuma mengisi placeholder tanggal/jam lalu mengirim lewat Resend (atau SMTP Gmail).

## Cara kerja

```
cron (Sen-Jum 20:00 WIB)
  └─ scripts/maganghub-reminder.sh
       └─ reminder.py
            ├─ baca dist/reminder.html  → isi {{TANGGAL}} {{JAM}} {{SITE}}
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
- Placeholder yang dikenali `reminder.py`: `{{TANGGAL}}`, `{{JAM}}`, `{{SITE}}`, `{{SITE_HOST}}`.
  Kalau menambah placeholder baru, tambahkan juga pasangannya di `render_html()`.
- Warna aksen utama `#73a5ca`, teks `#12212f` / `#5c7085`, background `#eef2f7`.
- Layout sudah diuji di lebar 640px dan 390px, plus dark mode (`prefers-color-scheme: dark`).
- `dist/reminder.html` ikut di-commit supaya pengingat tetap jalan walau Node tidak terpasang.

## Catatan

- Tidak ada kredensial di repo ini. Semua API key ada di `.env` di server.
- Kalau `dist/reminder.html` hilang, `reminder.py` pakai fallback HTML sederhana supaya
  pengingat tetap terkirim. Jalankan `npm run build` untuk mengembalikan tampilan penuh.
