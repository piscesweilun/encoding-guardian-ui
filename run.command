#!/bin/zsh

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

PORT=8000
URL="http://127.0.0.1:${PORT}/"

if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port ${PORT} is already in use. Opening ${URL}"
  open "$URL"
  read -r "?Press Enter to close..."
  exit 0
fi

open "$URL"

if command -v python3 >/dev/null 2>&1; then
  python3 server.py --host 127.0.0.1 --port "$PORT"
elif command -v python >/dev/null 2>&1; then
  python server.py --host 127.0.0.1 --port "$PORT"
else
  echo
  echo "Encoding Guardian failed to start. Install Python 3 and make sure 'python3' is available in PATH."
  read -r "?Press Enter to close..."
  exit 1
fi

status=$?
if [ "$status" -ne 0 ]; then
  echo
  echo "Encoding Guardian failed to start. Make sure Python is installed and available in PATH."
  read -r "?Press Enter to close..."
fi

exit "$status"
