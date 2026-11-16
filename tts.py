"""tts.py — Sesli yanıt (varsayılan İngilizce, ASSISTANT_LANG=tr ile Türkçe). Piper (tamamen yerel) veya edge-tts (internet gerekir).

TTS_BACKEND=piper (varsayılan) | edge  — biri başarısız olursa diğerine otomatik geçilir.
"""
import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import sounddevice as sd
import soundfile as sf

MODELS_DIR = Path(__file__).resolve().parent / "models"
BACKEND = os.getenv("TTS_BACKEND", "piper").lower()
LANG = os.getenv("ASSISTANT_LANG", "en").lower()  # "en" (varsayılan) veya "tr"
# Piper ses adı: <dil_BÖLGE>-<ses>-<kalite>  ör. en_US-lessac-medium, en_US-amy-medium, tr_TR-dfki-medium
PIPER_VOICE = os.getenv("PIPER_VOICE", "en_US-lessac-medium" if LANG == "en" else "tr_TR-dfki-medium")
# edge-tts: en-US-AriaNeural, en-US-GuyNeural, en-GB-SoniaNeural, tr-TR-EmelNeural ...
EDGE_VOICE = os.getenv("EDGE_VOICE", "en-US-AriaNeural" if LANG == "en" else "tr-TR-EmelNeural")


class TextToSpeech:
    def __init__(self, backend: str = BACKEND):
        self.order = ["piper", "edge"] if backend == "piper" else ["edge", "piper"]
        self._piper_model = None

    # ---------------------------------------------------------------- piper
    def _ensure_piper_model(self) -> Path:
        if self._piper_model:
            return self._piper_model
        name = PIPER_VOICE
        locale, voice, quality = name.split("-")  # en_US, lessac, medium
        base = (f"https://huggingface.co/rhasspy/piper-voices/resolve/main/"
                f"{locale.split('_')[0]}/{locale}/{voice}/{quality}/{name}")
        MODELS_DIR.mkdir(exist_ok=True)
        for suffix in (".onnx", ".onnx.json"):
            dest = MODELS_DIR / f"{name}{suffix}"
            if not dest.exists():
                print(f"[TTS] Piper ses modeli indiriliyor: {dest.name}")
                tmp = dest.with_suffix(dest.suffix + ".part")
                urllib.request.urlretrieve(base + suffix, tmp)
                tmp.rename(dest)
        self._piper_model = MODELS_DIR / f"{name}.onnx"
        return self._piper_model

    def _synth_piper(self, text: str, out: str) -> None:
        model = self._ensure_piper_model()
        subprocess.run(
            [sys.executable, "-m", "piper", "-m", str(model), "-f", out],
            input=text, text=True, capture_output=True, check=True, timeout=60,
        )

    # ------------------------------------------------------------------ edge
    def _synth_edge(self, text: str, out: str) -> None:
        import edge_tts

        asyncio.run(edge_tts.Communicate(text, EDGE_VOICE).save(out))

    # ---------------------------------------------------------------- oynatma
    @staticmethod
    def _play(path: str) -> None:
        try:
            data, sr = sf.read(path, dtype="float32")
        except Exception:  # libsndfile MP3 desteklemiyorsa ffmpeg ile çevir
            if not shutil.which("ffmpeg"):
                raise
            wav = path + ".wav"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, wav], check=True)
            data, sr = sf.read(wav, dtype="float32")
        sd.play(data, sr)
        sd.wait()

    @staticmethod
    def _clean(text: str) -> str:
        text = re.sub(r"```.*?```", " ", text, flags=re.S)
        text = re.sub(r"[*_#`>|~]", "", text)
        text = re.sub(r"https?://\S+", " bağlantı ", text)
        return re.sub(r"\s+", " ", text).strip()

    def speak(self, text: str) -> None:
        text = self._clean(text)
        if not text:
            return
        print(f"🔊 {text}")
        with tempfile.TemporaryDirectory() as tmp:
            for backend in self.order:
                out = os.path.join(tmp, "out.wav" if backend == "piper" else "out.mp3")
                try:
                    (self._synth_piper if backend == "piper" else self._synth_edge)(text, out)
                    self._play(out)
                    return
                except Exception as e:
                    err = getattr(e, "stderr", "") or e
                    print(f"[TTS] {backend} başarısız: {err}")
        print("[TTS] Hiçbir TTS motoru çalışmadı.")
