#!/bin/bash
#
# Registra el bot como LaunchAgent de macOS: arranca solo al iniciar sesión y
# se vuelve a levantar si se cae.
#
#   bash scripts/instalar-servicio.sh
#
set -euo pipefail

PROYECTO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$PROYECTO/.venv/bin/python"
ETIQUETA="com.folmedo.recetas-bot"
PLIST="$HOME/Library/LaunchAgents/$ETIQUETA.plist"
LOGS="$PROYECTO/logs"

if [ ! -x "$PYTHON" ]; then
  echo "No encuentro el entorno en $PYTHON" >&2
  echo "Créalo primero:  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi
if [ ! -f "$PROYECTO/.env" ]; then
  echo "Falta $PROYECTO/.env — el bot no arrancaría." >&2
  exit 1
fi

mkdir -p "$LOGS" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLISTFIN
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$ETIQUETA</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>-u</string>
        <string>-m</string>
        <string>recipe_bot</string>
    </array>

    <!-- El .env se lee relativo a la carpeta de trabajo. -->
    <key>WorkingDirectory</key>
    <string>$PROYECTO</string>

    <!-- launchd arranca con un PATH minimo: sin esto no encuentra ffmpeg
         y los videos fallarian aunque este instalado. -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$LOGS/bot.log</string>
    <key>StandardErrorPath</key>
    <string>$LOGS/bot.log</string>
</dict>
</plist>
PLISTFIN

launchctl unload -w "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"

echo "Listo. El bot arranca solo al iniciar sesión."
echo
echo "  Ver que corre:   launchctl list | grep recetas"
echo "  Ver el registro: tail -f $LOGS/bot.log"
echo "  Detenerlo:       launchctl unload -w $PLIST"
echo "  Volver a correr: launchctl load -w $PLIST"
