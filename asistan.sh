#!/usr/bin/env bash
# Sesli asistanı başlatır. Sanal ortamı kendisi kullanır, aktive etmene gerek yok.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

if [ ! -x "$DIR/.venv/bin/python" ]; then
    echo "Kurulum yapılmamış. Önce şunu çalıştır:  ./setup.sh"
    exit 1
fi

# Ollama çalışmıyorsa arka planda başlat
if ! curl -fs http://localhost:11434 >/dev/null 2>&1; then
    echo "Ollama başlatılıyor..."
    nohup ollama serve >/dev/null 2>&1 &
    sleep 3
fi

exec "$DIR/.venv/bin/python" main.py "$@"
