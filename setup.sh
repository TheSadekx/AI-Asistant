#!/usr/bin/env bash
# Fedora için tek komutla kurulum:  ./setup.sh
# Tekrar çalıştırmak güvenlidir (olan şeyleri atlar).
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"
DIR="$(pwd)"

echo "==> 1/6 NVIDIA sürücüsü kontrol ediliyor"
if command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name --format=csv,noheader
else
    echo "UYARI: NVIDIA sürücüsü çalışmıyor. Asistan yine çalışır ama Whisper CPU'da (yavaş) koşar."
    echo "Sürücü için: RPM Fusion ekle, 'sudo dnf install akmod-nvidia xorg-x11-drv-nvidia-cuda' kur, yeniden başlat."
fi

echo "==> 2/6 Sistem paketleri (sudo şifresi istenebilir)"
sudo dnf install -y python3-pip python3-devel gcc portaudio portaudio-devel libsndfile \
    ffmpeg-free xdg-utils gtk3 pipewire-utils pulseaudio-utils curl

echo "==> 3/6 Python sürümü seçiliyor"
if ! command -v python3.12 >/dev/null; then
    sudo dnf install -y python3.12 || echo "python3.12 kurulamadı, mevcut python3 denenecek."
fi
PY=""
for c in python3.12 python3.13 python3.11 python3; do
    if command -v "$c" >/dev/null; then PY="$c"; break; fi
done
echo "Kullanılacak: $PY ($($PY --version))"

echo "==> 4/6 Ollama ve model"
if ! command -v ollama >/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
fi
sudo systemctl enable --now ollama 2>/dev/null || true
sleep 2
ollama pull qwen2.5:7b

echo "==> 5/6 Python ortamı ve paketler"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "==> 6/6 Başlatıcı ve uygulama menüsü simgesi"
chmod +x asistan.sh
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/sesli-asistan.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=Sesli Asistan
Comment=Yerel sesli asistan
Exec=$DIR/asistan.sh
Path=$DIR
Terminal=true
Categories=Utility;
DESKTOP

echo
echo "Kurulum tamam!"
echo "Başlatmak için:  $DIR/asistan.sh"
echo "ya da uygulama menüsünde 'Sesli Asistan' ara."
