#!/bin/bash
# Claudromos for macOS: syncs your Garmin data (Personal API) to ~/Claudromos every 3 hours
# and rebuilds the dashboard (~/Claudromos/dashboards/claudromos.html) when new data arrives.
#
#   bash install.sh                 install or update (run from the cloned repo); asks for the API key once
#   bash install.sh update-key      replace an expired key
#   bash install.sh sync            run a sync now
#   bash install.sh rebuild         rebuild CSVs and the dashboard now
#   bash install.sh config          choose again what to sync and how far back
#   bash install.sh scope runs|all        runs = activities + weight; all = everything the API offers
#   bash install.sh history 1m|1y|3y|all  how far back to go (extending fetches only the older part)
#   bash install.sh diagnose        test the token request (prints status codes only)
#   bash install.sh uninstall       stop syncing, remove the key (keeps your data)
#
# Data folder: $CLAUDROMOS_DIR, default ~/Claudromos. An existing ~/Garmin install is moved there.
set -euo pipefail

DATA="${CLAUDROMOS_DIR:-$HOME/Claudromos}"
ENG="$DATA/.claudromos"
SRC="$(cd "$(dirname "$0")" && pwd)"
SVC="claudromos-garmin"
OLD_SVC="garmin-personal-api"
LABEL="local.claudromos.sync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
OLD_PLIST="$HOME/Library/LaunchAgents/local.garmin-sync.plist"
CONF="$ENG/config.json"
MODE="${1:-install}"

find_python() {
  for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 "$HOME/.homebrew/bin/python3"; do
    [ -x "$p" ] && "$p" -c 'import ssl, json, zipfile, venv' 2>/dev/null && { echo "$p"; return 0; }
  done
  if xcode-select -p >/dev/null 2>&1 && /usr/bin/python3 -c 'import ssl, venv' 2>/dev/null; then
    echo /usr/bin/python3; return 0
  fi
  return 1
}

save_key() {  # save_key <key>: fed through stdin so the key never appears in the process list
  case "$1" in *\"*|*\\*) echo "The key contains unexpected characters (quote or backslash)."; return 1 ;; esac
  printf 'add-generic-password -U -s "%s" -a "%s" -l "Claudromos: Garmin Personal API key" -T /usr/bin/security -w "%s"\n' \
    "$SVC" "$USER" "$1" | security -i >/dev/null
  local stored; stored="$(security find-generic-password -s "$SVC" -a "$USER" -w 2>/dev/null || true)"
  if [ "$stored" = "$1" ]; then echo "Key saved in your login Keychain (${#1} characters, verified)."; return 0; fi
  echo "WARNING: the Keychain returned ${#stored} characters but the key has ${#1}. Key not saved correctly."
  return 1
}

store_key() {
  # Not `security ... -w` prompting: its prompt silently truncates input at 128 characters.
  echo
  printf "Paste your Garmin Personal API key, then press Return (hidden): "
  IFS= read -rs KEY; echo
  KEY="$(printf '%s' "$KEY" | tr -d '[:space:]')"
  [ -n "$KEY" ] || { echo "No key entered."; exit 1; }
  save_key "$KEY" || { unset KEY; exit 1; }
  unset KEY
}

conf_get() {  # conf_get key default
  local v=""
  [ -f "$CONF" ] && v="$(sed -n "s/.*\"$1\": *\"\([^\"]*\)\".*/\1/p" "$CONF")"
  echo "${v:-$2}"
}

write_conf() {  # write_conf scope history
  mkdir -p "$ENG"
  printf '{"scope": "%s", "history": "%s", "tools_python": "%s"}\n' "$1" "$2" "$ENG/venv/bin/python" > "$CONF"
  echo "Settings: scope=$1, history=$2"
}

ask_config() {
  local s h
  echo
  echo "What should be synced?"
  echo "  1) Runs and weight: every activity with its original FIT file, plus weigh-ins"
  echo "  2) All Garmin data: the above plus full activity records, daily summaries, sleep, HRV,"
  echo "     VO2 max, steps, stress, hydration, Body Battery, and profile settings"
  read -r -p "Choose 1 or 2 [2]: " s
  case "$s" in 1) s=runs ;; *) s=all ;; esac
  echo
  echo "How much history should the first sync pull?"
  echo "  1) 1 month   2) 1 year   3) 3 years   4) All (back to your first activity)"
  read -r -p "Choose 1-4 [4]: " h
  case "$h" in 1) h=1m ;; 2) h=1y ;; 3) h=3y ;; *) h=all ;; esac
  write_conf "$s" "$h"
}

sync_py() { "$(cat "$ENG/python_path")" "$ENG/sync.py" "$@"; }

run_sync() {
  echo
  echo "Syncing $(conf_get scope all) data, history $(conf_get history all). A first sync can take a while"
  echo "(about 1 s per activity, more with 'all'). Progress: $DATA/logs/sync.log"
  CLAUDROMOS_DIR="$DATA" sync_py || true
  echo; echo "Result:"; cat "$DATA/status.json"; echo
}

migrate_from_garmin() {
  # Pre-Claudromos installs kept everything in ~/Garmin with the engine in ~/Garmin/.sync.
  local old="$HOME/Garmin"
  [ -d "$old/.sync" ] && [ ! -e "$DATA" ] || return 0
  echo
  echo "Found an existing install in $old."
  read -r -p "Move it to $DATA (keeps all data, nothing is downloaded again)? [Y/n]: " a
  case "$a" in n|N) echo "Keeping $old; installing into $DATA as a new folder."; return 0 ;; esac
  launchctl bootout "gui/$(id -u)" "$OLD_PLIST" 2>/dev/null || true
  rm -f "$OLD_PLIST"
  mv "$old" "$DATA"
  mkdir -p "$ENG" "$DATA/config"
  for f in state.json python_path; do [ -f "$DATA/.sync/$f" ] && mv "$DATA/.sync/$f" "$ENG/$f"; done
  if [ -f "$DATA/.sync/config.json" ]; then
    local s h; s="$(sed -n 's/.*"scope": *"\([^"]*\)".*/\1/p' "$DATA/.sync/config.json")"
    h="$(sed -n 's/.*"history": *"\([^"]*\)".*/\1/p' "$DATA/.sync/config.json")"
    write_conf "${s:-runs}" "${h:-1y}"
  fi
  [ -f "$DATA/.sync/overrides.json" ] && [ ! -f "$DATA/config/overrides.json" ] && mv "$DATA/.sync/overrides.json" "$DATA/config/"
  mv "$DATA/.sync" "$DATA/.sync-old"
  if ! security find-generic-password -s "$SVC" -a "$USER" >/dev/null 2>&1; then
    local k; k="$(security find-generic-password -s "$OLD_SVC" -a "$USER" -w 2>/dev/null || true)"
    if [ -n "$k" ] && save_key "$k"; then security delete-generic-password -s "$OLD_SVC" -a "$USER" >/dev/null 2>&1 || true; fi
    unset k
  fi
  echo "Moved to $DATA. The old engine files are in $DATA/.sync-old and can be deleted."
  echo "In the Claude desktop app, connect $DATA in place of $old."
}

case "$MODE" in
  update-key) store_key; run_sync; exit 0 ;;
  sync)       run_sync; exit 0 ;;
  rebuild)    CLAUDROMOS_DIR="$DATA" sync_py rebuild; echo "Dashboard: $DATA/dashboards/claudromos.html"; exit 0 ;;
  config)     ask_config; run_sync; exit 0 ;;
  scope)
    case "${2:-}" in runs|all) write_conf "$2" "$(conf_get history all)"; run_sync; exit 0 ;;
      *) echo "Usage: install.sh scope runs|all"; exit 1 ;; esac ;;
  history)
    case "${2:-}" in 1m|1y|3y|all) write_conf "$(conf_get scope all)" "$2"; run_sync; exit 0 ;;
      *) echo "Usage: install.sh history 1m|1y|3y|all"; exit 1 ;; esac ;;
  diagnose)   CLAUDROMOS_DIR="$DATA" sync_py diagnose; exit 0 ;;
  uninstall)
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    security delete-generic-password -s "$SVC" -a "$USER" >/dev/null 2>&1 || true
    echo "Stopped the sync and removed the key. Your data in $DATA was left in place."
    exit 0 ;;
  install) ;;
  *) echo "Unknown option: $MODE"; exit 1 ;;
esac

[ -f "$SRC/engine/sync.py" ] || { echo "Run the install from the cloned claudromos repo (it needs engine/)."; exit 1; }
PY="$(find_python)" || { echo "Python 3 isn't available. Run:  xcode-select --install   then run this installer again."; exit 1; }
echo "Using Python: $PY"

migrate_from_garmin
mkdir -p "$ENG/tools" "$ENG/dashboards" "$DATA/config" "$DATA/logs" "$DATA/dashboards" "$HOME/Library/LaunchAgents"
cp "$SRC/engine/sync.py" "$ENG/"
cp "$SRC"/engine/tools/*.py "$ENG/tools/"
cp "$SRC/engine/dashboards/claudromos.template.html" "$ENG/dashboards/"
cp "$SRC/install.sh" "$ENG/install.sh"
echo "$PY" > "$ENG/python_path"
echo "Engine installed in $ENG"

if [ ! -x "$ENG/venv/bin/python" ]; then
  echo "Setting up the tools environment (one-off)..."
  "$PY" -m venv "$ENG/venv"
fi
"$ENG/venv/bin/python" -m pip install -q --upgrade fitdecode || echo "WARNING: could not install fitdecode; dashboards won't build until it is installed."

[ -f "$CONF" ] || ask_config
grep -q tools_python "$CONF" || write_conf "$(conf_get scope all)" "$(conf_get history all)"

if ! security find-generic-password -s "$SVC" -a "$USER" >/dev/null 2>&1; then
  store_key
else
  echo "A key is already saved in the Keychain (use 'update-key' to replace it)."
fi

touch "$ENG/trigger"
cat > "$PLIST" <<PLEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>$ENG/sync.py</string></array>
  <key>EnvironmentVariables</key>
  <dict><key>CLAUDROMOS_DIR</key><string>$DATA</string></dict>
  <key>StartInterval</key><integer>10800</integer>
  <key>WatchPaths</key>
  <array><string>$ENG/trigger</string></array>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$DATA/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$DATA/logs/launchd.err.log</string>
</dict>
</plist>
PLEOF
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Scheduled: sync every 3 hours (catches up after the Mac wakes), and whenever $ENG/trigger is touched."

run_sync
echo "Done. Data: $DATA   Dashboard: $DATA/dashboards/claudromos.html"
echo "Next: in Claude, add the claudromos-coach skill and say \"set me up\"."
