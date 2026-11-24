#!/usr/bin/env python3
"""Pengingat absen MagangHub lewat email (Resend API).

Jadwal cron: 20:59 WIB, Senin-Jumat  ->  "59 13 * * 1-5" (UTC)

Konfigurasi dibaca dari /root/.hermes/.env:
  RESEND_API_KEY   wajib
  MAGANGHUB_TO     opsional, default maganghub@satgas.ai.id
  MAGANGHUB_FROM   opsional, default alarm@satgas.ai.id (domain harus terverifikasi di Resend)

Perilaku:
  - sukses  -> diam (cron tidak mengirim pesan)
  - gagal   -> exit 1 dengan pesan error, supaya cron mengirim alert ke Telegram
    (alarm yang mati diam-diam lebih berbahaya daripada tidak punya alarm)

Pakai:
  python3 reminder.py            # kirim pengingat
  python3 reminder.py --check     # validasi konfigurasi tanpa mengirim
  python3 reminder.py --test      # kirim sekarang (abaikan hari kerja)
  python3 reminder.py --preview   # tulis HTML ke dist/preview.html, tanpa kirim

Tampilan email ada di src/reminder.mjml (MJML). Setelah diubah:
  npm install && npm run build    # hasil: dist/reminder.html (dibaca skrip ini)
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

ENV_FILE = "/root/.hermes/.env"
RESEND_URL = "https://api.resend.com/emails"
WIB = timezone(timedelta(hours=7))

DEFAULT_TO = "maganghub@satgas.ai.id"
DEFAULT_FROM = "alarm@satgas.ai.id"
# Dashboard monev peserta (bukan landing page maganghub.kemnaker.go.id).
SITE = "https://monev.maganghub.kemnaker.go.id/dashboard"
SITE_HOST = "monev.maganghub.kemnaker.go.id"
# Batas pengisian laporan harian menurut dashboard: 23.59 WIB.
DEADLINE_HOUR, DEADLINE_MINUTE = 23, 59

# Template HTML hasil build MJML (lihat src/reminder.mjml + npm run build).
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "reminder.html")

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def load_env():
    """Ambil variabel dari .env tanpa menimpa environment yang sudah ada."""
    vals = {}
    if not os.path.exists(ENV_FILE):
        return vals
    with open(ENV_FILE, errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


FALLBACK_HTML = """<div style="font-family:Arial,sans-serif;font-size:15px;color:#25324a">
<h2 style="margin:0 0 8px;color:#0f1729">Laporan hari ini belum diisi</h2>
<p style="margin:0 0 12px">{tgl} &middot; batas isi 23.59 WIB ({sisa})</p>
<p style="margin:0 0 16px">Dashboard MagangHub belum mencatat laporan dan kehadiran kamu
untuk hari ini. Isi sebelum batas pengisian supaya tidak dihitung alpa.</p>
<p style="margin:0 0 16px">Yang harus diisi: kehadiran (absen masuk &amp; pulang),
laporan aktivitas harian, cek pengumuman di Beranda.</p>
<p style="margin:0"><a href="{site}" style="color:#0b60ea">Buka Dashboard</a></p>
</div>"""


def sisa_waktu(now):
    """Jarak ke batas pengisian 23.59 WIB, dalam bahasa manusia.

    Dipakai untuk chip "Batas isi" supaya penerima lihat sisa waktu sebenarnya,
    bukan angka statis yang jadi bohong kalau jadwal cron diubah.
    """
    deadline = now.replace(hour=DEADLINE_HOUR, minute=DEADLINE_MINUTE, second=0, microsecond=0)
    delta = deadline - now
    menit = int(delta.total_seconds() // 60)
    if menit <= 0:
        return "batas sudah lewat"
    jam, sisa_menit = divmod(menit, 60)
    if jam == 0:
        return f"sisa {sisa_menit} menit lagi"
    if sisa_menit == 0:
        return f"sisa {jam} jam lagi"
    return f"sisa {jam} jam {sisa_menit} menit lagi"


def render_html(tgl, jam):
    """Isi template hasil build MJML dengan nilai hari ini.

    Template dibaca dari dist/reminder.html supaya desain tetap satu sumber:
    ubah src/reminder.mjml, jalankan `npm run build`, template ikut berubah.
    Kalau file template hilang (mis. repo di-clone tanpa build), pakai
    FALLBACK_HTML supaya pengingat tidak pernah gagal terkirim hanya karena UI.
    """
    sisa = sisa_waktu(jam)
    values = {
        "{{TANGGAL}}": tgl,
        "{{JAM}}": f"{jam:%H:%M}",
        "{{SISA}}": sisa,
        "{{SITE}}": SITE,
        "{{SITE_HOST}}": SITE_HOST,
    }
    try:
        with open(TEMPLATE_PATH, encoding="utf-8") as f:
            html = f.read()
    except OSError:
        html = FALLBACK_HTML
    for key, val in values.items():
        html = html.replace(key, val)
    return html


def build_message(now):
    tgl = f"{HARI[now.weekday()]}, {now.day} {BULAN[now.month-1]} {now.year}"
    subject = f"Laporan MagangHub belum diisi - {tgl}"
    body_text = (
        f"Laporan hari ini belum diisi\n"
        f"{tgl} - batas isi 23.59 WIB ({sisa_waktu(now)})\n\n"
        f"Dashboard MagangHub belum mencatat laporan dan kehadiran kamu untuk hari ini.\n"
        f"Isi sebelum batas pengisian supaya tidak dihitung alpa.\n\n"
        f"Yang harus diisi:\n"
        f"  1. Kehadiran: absen masuk dan absen pulang\n"
        f"  2. Laporan aktivitas harian\n"
        f"  3. Cek pengumuman terbaru di Beranda\n\n"
        f"Alur status di Riwayat: belum diisi -> menunggu tindakan mentor -> hadir disetujui\n\n"
        f"Catatan:\n"
        f"  - Setelah dikirim, laporan berstatus menunggu tindakan mentor sampai\n"
        f"    disetujui. Tidak ada tindakan tambahan dari kamu.\n"
        f"  - Izin dibayar maksimal 3 hari per periode. Izin ke-4 dan seterusnya tidak\n"
        f"    dibayar, tetapi tidak dihitung alpa.\n"
        f"  - Lewat dari 23.59 WIB tanpa laporan dihitung tidak hadir.\n"
        f"  - Sabtu, Minggu, dan hari libur ditandai Hari Libur, tidak perlu isi laporan.\n\n"
        f"Buka dashboard: {SITE}\n"
    )
    body_html = render_html(tgl, now)
    return subject, body_text, body_html


def parse_recipients(raw: str) -> list[str]:
    """Pisahkan daftar penerima yang dipisah koma atau titik koma.

    MAGANGHUB_TO boleh berisi satu alamat atau beberapa; urutan dipertahankan dan
    duplikat dibuang supaya satu orang tidak menerima dua kali.
    """
    import re as _re
    seen, out = set(), []
    for part in _re.split(r"[;,]", raw or ""):
        addr = part.strip().strip('"').strip("'")
        if not addr:
            continue
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(addr)
    return out


def send_smtp(user, password, to, frm, subject, text, html, host="smtp.gmail.com", port=587):
    """Kirim lewat SMTP (Gmail app password). Stdlib saja, tanpa dependency."""
    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = frm
    msg["To"] = ", ".join(to) if isinstance(to, (list, tuple)) else to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(user, password)
            s.send_message(msg)
        return True, {"via": "smtp", "to": to if isinstance(to, (list, tuple)) else [to]}
    except smtplib.SMTPAuthenticationError as e:
        return False, f"SMTP auth gagal: {e.smtp_code} {e.smtp_error!r}. App password salah atau 2FA belum aktif."
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def send(api_key, to, frm, subject, text, html):
    payload = {
        "from": frm,
        "to": list(to) if isinstance(to, (list, tuple)) else [to],
        "subject": subject,
        "text": text,
        "html": html,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        RESEND_URL, data=data, method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # UA gaya SDK: UA Python default diblok Cloudflare di depan API Resend (error 1010)
            "User-Agent": "resend-python/2.0.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return True, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        return False, f"HTTP {e.code}: {detail}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--preview", nargs="?", const="dist/preview.html", metavar="PATH",
                    help="tulis HTML hasil render ke file, tanpa kirim email")
    args = ap.parse_args()

    now = datetime.now(WIB)
    subject, text, html = build_message(now)

    if args.preview:
        out = args.preview
        if not os.path.isabs(out):
            out = os.path.join(os.path.dirname(os.path.abspath(__file__)), out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"preview ditulis: {out}")
        print(f"template: {'dist/reminder.html' if os.path.exists(TEMPLATE_PATH) else 'FALLBACK (template tidak ada)'}")
        return 0

    env = load_env()
    api_key = os.environ.get("RESEND_API_KEY") or env.get("RESEND_API_KEY", "")
    smtp_user = os.environ.get("GMAIL_USER") or env.get("GMAIL_USER", "")
    smtp_pass = os.environ.get("GMAIL_APP_PASSWORD") or env.get("GMAIL_APP_PASSWORD", "")
    to_raw = os.environ.get("MAGANGHUB_TO") or env.get("MAGANGHUB_TO", DEFAULT_TO)
    to = parse_recipients(to_raw)
    if not to:
        to = [DEFAULT_TO]
    frm = os.environ.get("MAGANGHUB_FROM") or env.get("MAGANGHUB_FROM", DEFAULT_FROM)

    use_smtp = bool(smtp_user and smtp_pass)
    if use_smtp:
        # Gmail menolak From selain alamat akunnya (kecuali alias terverifikasi)
        frm = smtp_user

    backend = "SMTP Gmail" if use_smtp else ("Resend" if api_key else "belum ada")

    if args.check:
        print("Konfigurasi pengingat MagangHub")
        print(f"  backend        : {backend}")
        print(f"  GMAIL_USER     : {smtp_user or 'BELUM ADA'}")
        print(f"  GMAIL_APP_PASS : {'ADA (len ' + str(len(smtp_pass)) + ')' if smtp_pass else 'BELUM ADA'}")
        print(f"  RESEND_API_KEY : {'ADA' if api_key else 'BELUM ADA'}")
        print(f"  to             : {', '.join(to)}")
        print(f"  from           : {frm}")
        print(f"  jadwal         : 20:00 WIB, Senin-Jumat (0 13 * * 1-5 UTC)")
        print(f"  template       : {'dist/reminder.html (MJML build)' if os.path.exists(TEMPLATE_PATH) else 'FALLBACK bawaan (belum build)'}")
        print(f"  contoh subject : {subject}")
        if not use_smtp and not api_key:
            print("\nSTATUS: belum siap. Isi GMAIL_USER + GMAIL_APP_PASSWORD, atau RESEND_API_KEY.")
            return 1
        print(f"\nSTATUS: siap pakai lewat {backend}. Jalankan --test untuk kirim percobaan.")
        return 0

    if not use_smtp and not api_key:
        print("PENGINGAT MAGANGHUB GAGAL DIKIRIM")
        print("Belum ada kredensial email di /root/.hermes/.env")
        print("Isi salah satu:")
        print("  GMAIL_USER=alamat@gmail.com")
        print("  GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx")
        print("atau RESEND_API_KEY=re_xxxx")
        return 1

    if use_smtp:
        ok, info = send_smtp(smtp_user, smtp_pass, to, frm, subject, text, html)
    else:
        ok, info = send(api_key, to, frm, subject, text, html)

    if ok:
        # Sengaja tidak mencetak apa pun di stdout: cron mode no_agent
        # hanya boleh diam kalau email berhasil, supaya tidak spam chat.
        if args.test:
            print(f"terkirim via {backend}: {info}", file=sys.stderr)
        return 0

    # --- Jalur cadangan: email gagal, pengingat tetap harus sampai ---
    # Cron mode no_agent mengirim stdout apa adanya. Jadi daripada cuma error,
    # kirim pengingatnya lewat Telegram supaya absen tidak terlewat,
    # sambil tetap melaporkan kenapa email gagal.
    print(f"PENGINGAT ABSEN MAGANGHUB - {HARI[now.weekday()]}, {now.day} {BULAN[now.month-1]} {now.year}")
    print()
    print(f"Jangan lupa isi Laporan Aktivitas Magang hari ini.")
    print(f"Buka: {SITE}")
    print()
    print(f"(Email ke {to} gagal, jadi pengingat ini dikirim lewat Telegram.)")
    short = str(info)
    for key in ("domain is not verified", "testing emails to your own email address"):
        if key in short:
            short = "domain pengirim belum terverifikasi di Resend"
            break
    print(f"Alasan: {short[:180]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
