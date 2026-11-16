# Yerel Sesli Asistan

Tamamen bilgisayarında çalışan sesli asistan (Fedora Linux + NVIDIA GPU önerilir).

- **Dinleme:** faster-whisper (CUDA)
- **Beyin:** Ollama + qwen2.5:7b (uygulama açma, komut çalıştırma, ses ayarı...)
- **Konuşma:** Piper (yerel) veya edge-tts (internet gerekir)

## Kurulum

```bash
git clone <depo-adresi> sesli-asistan   # veya zip'i aç
cd sesli-asistan
chmod +x setup.sh asistan.sh
./setup.sh
```

NVIDIA sürücüsü kurulu olmalı (`nvidia-smi` çalışmalı). Sürücü yoksa asistan CPU'da çalışır ama yavaştır.

## Çalıştırma

```bash
./asistan.sh
```

veya uygulama menüsünden **Sesli Asistan**. Kapatmak için "goodbye" / "close the program" de ya da Ctrl+C.

## Ayarlar (ortam değişkenleri)

| Değişken | Örnek | Anlamı |
|---|---|---|
| `ASSISTANT_LANG` | `en` (varsayılan), `tr` | Dil |
| `WHISPER_MODEL` | `small.en`, `small` | Tanıma modeli |
| `TTS_BACKEND` | `piper`, `edge` | Ses motoru |
| `PIPER_VOICE` | `en_US-amy-medium` | Piper sesi |
| `EDGE_VOICE` | `en-US-GuyNeural` | edge-tts sesi |
| `AUDIO_INPUT_DEVICE` | `5` | Mikrofon numarası (`python -m sounddevice`) |
| `VAD_THRESHOLD` | `0.03` | Ses eşiği |

Örnek: `ASSISTANT_LANG=tr WHISPER_MODEL=small ./asistan.sh`

## Güvenlik

`run_command` kabuk kullanmaz. `ls`, `df` gibi salt-okunur komutlar doğrudan çalışır, diğerleri sesli onay ister.
`sudo`, `rm -r`, `dd`, `mkfs` vb. engellidir.
