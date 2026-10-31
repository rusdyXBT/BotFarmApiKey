#!/usr/bin/env python3
"""Dahl key farm — 1 file simpel. Signup akun inference.dahl.global →
api_key + 100M token gratis per akun.

Pakai:
  python3 farm.py --count 10                      # 10 akun, delay default 60-75s
  python3 farm.py --count 50 --delay 110 140      # pacing lambat (anti-flag, disarankan)
  python3 farm.py --count 50 --proxy 1.2.3.4:8080          # 1 proxy utk semua
  python3 farm.py --count 50 --proxy user:pass@1.2.3.4:8080  # proxy dgn auth
  python3 farm.py --count 50 --proxies proxies.txt         # rotasi proxy otomatis

Proxy opsional — tanpa proxy pakai IP VPS langsung. Format proxy bebas:
host:port | http://host:port | http://user:pass@host:port | socks5://host:port
Kalau 5 fail beruntun (IP keflag Turnstile): tunggu ±25 menit, jalan lagi.
"""
import argparse
import json
import os
import random
import re
import string
import subprocess
import sys
import time
import urllib.request

import requests
from playwright.sync_api import sync_playwright

BASE = "https://inference.dahl.global"
HERE = os.path.dirname(os.path.abspath(__file__))
TSV = os.path.join(HERE, "accounts.tsv")
STATE = os.path.join(HERE, "farm_state.json")
LOG = os.path.join(HERE, "farm.log")
SHOTS = os.path.join(HERE, "screenshots")
CHROME_INFO = os.path.join(HERE, ".chrome.json")

DISPLAY = ":80"
PORT = 9225
PROFILE = os.path.join(HERE, "chrome-prof")
ALLOC = 100_000_000

ADJ = ["fierce", "cosmic", "gentle", "amber", "lunar", "misty", "mellow", "proud",
       "crimson", "bold", "polar", "tidy", "brave", "daring", "keen", "cozy",
       "rusty", "icy", "kind", "wild", "calm", "bright", "humble", "sunny",
       "quiet", "noble", "swift", "lucky", "warm", "epic", "zesty"]
ANI = ["pebble", "robin", "moose", "cloud", "cedar", "comet", "wren", "otter",
       "maple", "whale", "pine", "lynx", "falcon", "stork", "orca", "panda",
       "fern", "dove", "eagle", "spruce", "heron", "finch", "badger", "ember",
       "frost", "honey", "juniper", "signal", "storm", "willow"]


def log(m):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {m}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"accounts": [], "used_usernames": []}


def save_state(st):
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE)


def gen_username(used):
    while True:
        pre = f"{random.choice(ADJ)}_{random.choice(ANI)}_"
        n = 20 - len(pre)
        suf = str(random.randint(100, 999)) + "".join(
            random.choices(string.ascii_lowercase, k=max(2, n - 3)))
        u = (pre + suf)[:20]
        if u not in used:
            return u


# ---------------- proxy ----------------
def norm_proxy(p):
    """'1.2.3.4:8080' → 'http://1.2.3.4:8080'."""
    return p if "://" in p else "http://" + p


def split_proxy(p):
    """→ (scheme, host, port, user, pass)."""
    p = norm_proxy(p)
    m = re.match(r"(https?|socks5)://(?:([^:]+):([^@]*)@)?([^:]+):(\d+)", p)
    if not m:
        raise ValueError(f"proxy format aneh: {p}")
    return m.group(1), m.group(4), int(m.group(5)), m.group(2) or "", m.group(3) or ""


def make_auth_ext(scheme, host, port, user, pwd):
    """Chrome gak dukung user:pass di --proxy-server → trik: extension yang
    set proxy + jawab challenge auth otomatis."""
    ext = os.path.join(HERE, ".proxy-auth-ext")
    os.makedirs(ext, exist_ok=True)
    json.dump({"manifest_version": 2, "name": "pa", "version": "1.0",
               "permissions": ["webRequest", "webRequestAuthProvider", "proxy"],
               "background": {"scripts": ["bg.js"], "persistent": True}},
              open(os.path.join(ext, "manifest.json"), "w"))
    bg = (
        "var cfg={mode:'fixed_servers',rules:{singleProxy:{scheme:'%(s)s',"
        "host:'%(h)s',port:%(p)d},bypassList:[]}};"
        "chrome.proxy.settings.set({value:cfg,scope:'regular'},function(){});"
    ) % {"s": scheme, "h": host, "p": port}
    if user:
        bg += (
            "chrome.webRequest.onAuthRequired.addListener("
            "function(d,cb){cb({authCredentials:{username:'%(u)s',password:'%(w)s'}});},"
            "{urls:['<all_urls>']},['asyncBlocking']);"
        ) % {"u": user, "w": pwd}
    open(os.path.join(ext, "bg.js"), "w").write(bg)
    return ext


# ---------------- chrome ----------------
def chrome_alive():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=3)
        return True
    except Exception:
        return False


def chrome_kill():
    subprocess.run(["pkill", "-f", f"--remote-debugging-port={PORT}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)


def ensure_chrome(proxy=None):
    """Start Chrome kalau belum jalan / proxy berubah (→ restart dgn proxy baru)."""
    info = json.load(open(CHROME_INFO)) if os.path.exists(CHROME_INFO) else {}
    if chrome_alive() and info.get("proxy", "") == (proxy or ""):
        return
    chrome_kill()
    if not os.path.exists("/tmp/.X11-unix/X80"):
        subprocess.Popen(["Xvfb", DISPLAY, "-screen", "0", "1280x1490x24"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
    args = ["google-chrome", f"--user-data-dir={PROFILE}",
            f"--remote-debugging-port={PORT}", "--no-first-run",
            "--no-default-browser-check", "--no-sandbox",
            "--window-size=1280,1490", "--window-position=0,0", "about:blank"]
    if proxy:
        scheme, host, port, user, pwd = split_proxy(proxy)
        ext = make_auth_ext(scheme, host, port, user, pwd)
        args.append(f"--proxy-server={scheme}://{host}:{port}")
        args += [f"--load-extension={ext}", f"--disable-extensions-except={ext}"]
        log(f"chrome pakai proxy {scheme}://{host}:{port}" + (" (+auth)" if user else ""))
    subprocess.Popen(args, env=dict(os.environ, DISPLAY=DISPLAY),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=3)
            json.dump({"proxy": proxy or ""}, open(CHROME_INFO, "w"))
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("chrome gak mau hidup di CDP %d" % PORT)


# ---------------- signup (metode terbukti: CDP mouse click) ----------------
def browser_signup(page, username, shot):
    page.goto("about:blank", wait_until="domcontentloaded", timeout=30000)
    page.goto(BASE + "/account", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(12000)
    page.evaluate("""() => {
        const b = Array.from(document.querySelectorAll('button')).find(
            e => e.innerText.trim().toLowerCase() === 'create account');
        if (b) b.click();
    }""")
    page.wait_for_timeout(6000)

    inp = page.locator("#signup-username")
    if inp.count() == 0:
        raise RuntimeError("form gak muncul (session nyangkut?)")
    inp.click()
    page.keyboard.press("Control+a")
    inp.type(username, delay=60)

    # posisi checkbox: iframe turnstile (clientWidth>100) kalau nemu,
    # fallback offset dari username field. KLIK PAKE MOUSE — JS click gak trusted.
    cb = page.evaluate("""() => {
        const ifr = Array.from(document.querySelectorAll('iframe'))
            .find(f => f.clientWidth > 100);
        if (ifr) { const r = ifr.getBoundingClientRect();
            return {x: r.x + 26, y: r.y + r.height/2}; }
        const r = document.querySelector('#signup-username').getBoundingClientRect();
        return {x: r.x + r.width/2 - 273, y: r.y + r.height/2 + 88};
    }""")
    page.mouse.move(int(cb["x"]), int(cb["y"]))
    time.sleep(0.8)
    page.mouse.click(int(cb["x"]), int(cb["y"]))

    solved = False
    for attempt in range(2):
        for _ in range(20):
            time.sleep(3)
            st = page.evaluate("""() => ({
                tok: ((document.querySelector('input[name=cf-turnstile-response]')||{}).value||'').length,
                btn: (Array.from(document.querySelectorAll('button')).filter(b=>b.offsetParent)
                      .find(e => /checking|create/i.test(e.innerText)) || {innerText:''}).innerText.trim(),
            })""")
            if st["tok"] > 0 and "checking" not in st["btn"].lower():
                solved = True
                break
        if solved:
            break
        page.mouse.click(int(cb["x"]), int(cb["y"]))  # klik ke-2
    if not solved:
        page.screenshot(path=shot + "_fail.png")
        raise RuntimeError("turnstile gak solve")

    # submit juga via mouse (JS click gak trigger handler dgn benar)
    sb = page.evaluate("""() => {
        const b = Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent)
            .find(e => /create account/i.test(e.innerText) && !e.disabled);
        if (!b) return null;
        const r = b.getBoundingClientRect();
        return {x: r.x + r.width/2, y: r.y + r.height/2};
    }""")
    if not sb:
        page.screenshot(path=shot + "_nosubmit.png")
        raise RuntimeError("submit disabled / gak ada")
    page.mouse.click(int(sb["x"]), int(sb["y"]))
    page.wait_for_timeout(9000)

    body = page.inner_text("body")
    if "too many" in body.lower():
        raise RuntimeError("rate_limited")
    m = re.search(r"Fingerprint\s*\n?\s*([0-9a-f]{32})", body) or \
        re.search(r"\b([0-9a-f]{32})\b", body)
    if not m:
        page.screenshot(path=shot + "_nofp.png")
        raise RuntimeError("fingerprint gak ketemu")
    return m.group(1)


def api_followup(fp, proxy=None):
    """signin + ambil key + allocate 100M — murni API, gak perlu browser."""
    s = requests.Session()
    if proxy:
        p = norm_proxy(proxy)
        s.proxies = {"http": p, "https": p}
    r = s.post(BASE + "/v1/auth/signin", json={"fingerprint": fp}, timeout=30)
    r.raise_for_status()
    user = r.json()["user"]
    keys = s.get(BASE + "/v1/account/keys", timeout=30).json()["keys"]
    if not keys:
        raise RuntimeError("gak ada key")
    key_id, token = keys[0]["id"], keys[0]["token"]
    bal = s.post(BASE + "/v1/account/allocate",
                 json={"key_id": key_id, "amount": ALLOC}, timeout=30).json()
    return dict(username=user["username"], api_key=token, fingerprint=fp,
                user_id=user["user_id"], key_id=key_id,
                balance=bal["key"]["available_tokens"],
                created=time.strftime("%Y-%m-%dT%H:%M:%S+0800"))


def append_tsv(a):
    new = not os.path.exists(TSV)
    with open(TSV, "a") as f:
        if new:
            f.write("username\tapi_key\tfingerprint\tuser_id\tkey_id\tbalance\tcreated\n")
        f.write("\t".join(str(a[k]) for k in
                          ("username", "api_key", "fingerprint", "user_id",
                           "key_id", "balance", "created")) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--delay", type=int, nargs=2, default=[60, 75],
                    help="delay min max antar akun (detik). 110 140 = anti-flag")
    ap.add_argument("--proxy", help="host:port | http://user:pass@host:port | socks5://host:port")
    ap.add_argument("--proxies", help="file daftar proxy (1/baris), rotasi otomatis saat IP keflag")
    args = ap.parse_args()

    proxies = []
    if args.proxies:
        proxies = [l.strip() for l in open(args.proxies)
                   if l.strip() and not l.startswith("#")]
    cur_proxy = args.proxy or (proxies[0] if proxies else None)

    os.makedirs(SHOTS, exist_ok=True)
    st = load_state()
    used = set(st["used_usernames"]) | {a["username"] for a in st["accounts"]}
    ok = fails = 0
    t0 = time.time()

    with sync_playwright() as pw:
        for i in range(args.count):
            try:
                ensure_chrome(cur_proxy)
                b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
                ctx = b.contexts[0]
                page = (ctx.pages or [ctx.new_page()])[0]
            except Exception as e:
                log(f"chrome error: {str(e)[:100]}")
                chrome_kill()
                time.sleep(5)
                continue

            username = gen_username(used)
            shot = os.path.join(SHOTS, username)
            via = ""
            if cur_proxy:
                sc, ho, po, _, _ = split_proxy(cur_proxy)
                via = f" via {sc}://{ho}"
            log(f"[{i+1}/{args.count}] signup {username}{via}")
            try:
                # clear CUMA cookie session (cf_clearance jgn dihapus —
                # kalau hilang, iframe Turnstile gak ke-render)
                ctx.clear_cookies(name="dahl_session")
                fp = browser_signup(page, username, shot)
                acc = api_followup(fp, cur_proxy)
                if acc["balance"] < ALLOC:
                    raise RuntimeError(f"balance aneh: {acc['balance']}")
                append_tsv(acc)
                used.add(acc["username"])
                st["used_usernames"].append(acc["username"])
                st["accounts"].append(acc)
                save_state(st)
                ok += 1
                fails = 0
                log(f"[{i+1}/{args.count}] OK {acc['username']} "
                    f"key={acc['api_key'][:12]}… bal={acc['balance']:,} total_ok={ok}")
            except Exception as e:
                fails += 1
                log(f"[{i+1}/{args.count}] FAIL {username}: {str(e)[:100]} (fails={fails})")
                if fails >= 5:
                    if proxies:
                        nxt = proxies[(proxies.index(cur_proxy) + 1) % len(proxies)] \
                            if cur_proxy in proxies else proxies[0]
                        sc, ho, po, _, _ = split_proxy(nxt)
                        log(f"ABORT IP ini — rotasi proxy → {sc}://{ho}")
                        cur_proxy = nxt
                        chrome_kill()
                        fails = 0
                        continue
                    log("ABORT: 5 fail beruntun (IP kemungkinan keflag Turnstile — "
                        "tunggu ±25 menit lalu jalan lagi)")
                    break
                time.sleep(random.randint(120, 160) if fails >= 2
                           else random.randint(*args.delay))
                continue

            if i < args.count - 1:
                d = random.randint(*args.delay)
                log(f"sleep {d}s")
                time.sleep(d)

    log(f"SELESAI: ok={ok} fail={fails} durasi={(time.time()-t0)/60:.0f}m "
        f"total_state={len(st['accounts'])}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
