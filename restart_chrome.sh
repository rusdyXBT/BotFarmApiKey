#!/bin/bash
# Restart Chrome farm — profil bersih (CF state fresh), CDP :9225, Xvfb :80
# Dipanggil otomatis oleh farm.py saat perlu; manual juga bisa:
#   bash restart_chrome.sh
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for pid in $(ls /proc | grep -E '^[0-9]+$'); do
  if [ -r "/proc/$pid/cmdline" ]; then
    cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
    case "$cmd" in
      *"remote-debugging-port=9225"*) kill "$pid" 2>/dev/null ;;
    esac
  fi
done
sleep 1
rm -rf "$DIR/chrome-prof"
if [ ! -e /tmp/.X11-unix/X80 ]; then
  Xvfb :80 -screen 0 1280x1490x24 > /dev/null 2>&1 &
  sleep 2
fi
DISPLAY=:80 nohup google-chrome \
  --user-data-dir="$DIR/chrome-prof" \
  --remote-debugging-port=9225 \
  --no-first-run --no-default-browser-check --no-sandbox \
  --window-size=1280,1490 --window-position=0,0 "about:blank" \
  > /dev/null 2>&1 &
sleep 5
curl -sS http://127.0.0.1:9225/json/version | head -c 100
echo
echo "chrome siap (CDP :9225, Xvfb :80)"
