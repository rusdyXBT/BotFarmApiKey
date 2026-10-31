# Dahl Key Farm

Auto-signup akun [inference.dahl.global](https://inference.dahl.global) dalam jumlah
besar → tiap akun dapat **API key + 100 juta token gratis** (in+out, tidak expired).

Bypass Cloudflare Turnstile memakai Chrome real lewat CDP: klik checkbox &
tombol submit pakai input mouse level CDP (trusted event), jadi lolos deteksi
automation tanpa solver eksternal.

## Isi paket

| File | Fungsi |
|---|---|
| `farm.py` | Script utama — signup, solve turnstile, ambil key, allocate 100M token |
| `restart_chrome.sh` | Restart Chrome bersih (CDP :9225 + Xvfb :80) |
| `requirements.txt` | Dependensi Python |

## Setup

```bash
pip install -r requirements.txt
playwright install chromium   # fallback; utamanya butuh google-chrome terinstall
```

Butuh `google-chrome` + `Xvfb` di PATH (Debian/Ubuntu: `apt install xvfb` + install
Chrome stable).

## Pemakaian

```bash
# 10 akun, delay default 60-75s
python3 farm.py --count 10

# PACING LAMBAT = anti-flag (disarankan untuk batch besar)
python3 farm.py --count 50 --delay 110 140

# pakai 1 proxy (opsional)
python3 farm.py --count 50 --proxy 1.2.3.4:8080
python3 farm.py --count 50 --proxy http://user:pass@1.2.3.4:8080
python3 farm.py --count 50 --proxy socks5://1.2.3.4:1080

# rotasi proxy otomatis saat IP keflag (file 1 proxy per baris)
python3 farm.py --count 100 --proxies proxies.txt
```

## Output

- `accounts.tsv` — accumulator: `username, api_key, fingerprint, user_id, key_id, balance, created`
- `farm_state.json` — state resume aman (username terpakai gak didaur ulang)
- `farm.log` — log readable
- `screenshots/` — otomatis muncul HANYA saat fail (untuk debug)

## Catatan penting ( hasil riset lapangan )

1. **Turnstile flag per-IP**: ±16-25 challenge cepat berturut (delay 60-75s) →
   submit mulai ditolak server walau solve lokal sukses. Obat:
   - delay `110 140` → 24+ sukses berturut tanpa flag, atau
   - kalau sudah keflag: **tunggu ±25 menit**, flag hilang sendiri.
2. Script auto-berhenti setelah 5 fail beruntun — itu normal, bukan bug.
3. Delay default 60-75s cocok untuk batch kecil (<15 akun).
4. `--proxy` opsional: tanpa proxy = pakai IP mesin langsung.
5. Key langsung aktif dengan 100M token (auto-allocate via API setelah signup).

## Flow teknis singkat

```
Xvfb :80 → Chrome (CDP 9225) → buka /account → klik "Create account"
→ isi username → page.mouse.click checkbox Turnstile (layout-aware)
→ tunggu token (±3-10s) → klik submit (mouse) → fingerprint tampil
→ API: /v1/auth/signin → /v1/account/keys → /v1/account/allocate 100M
→ append accounts.tsv
```
