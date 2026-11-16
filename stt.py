"""stt.py — Mikrofon kaydı (sounddevice) + faster-whisper (CUDA) ile Türkçe konuşma tanıma."""
import glob
import os
import queue
import sys
import time
from collections import deque

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
BLOCK_SEC = 0.03  # 30 ms'lik bloklar

LANG = os.getenv("ASSISTANT_LANG", "en").lower()  # "en" (varsayılan) veya "tr"
# İngilizce için: base.en / small.en / medium.en — Türkçe için: base / small / medium
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base.en" if LANG == "en" else "base")
INPUT_DEVICE = os.getenv("AUDIO_INPUT_DEVICE")  # None -> varsayılan mikrofon
INPUT_DEVICE = int(INPUT_DEVICE) if INPUT_DEVICE and INPUT_DEVICE.isdigit() else INPUT_DEVICE

# Whisper'ın sessizlikte sıkça uydurduğu cümleler
HALLUCINATIONS = (
    "altyazı",
    "izlediğiniz için teşekkür",
    "abone olmayı unutmayın",
    "bir sonraki videoda görüşmek",
    "thanks for watching",
    "thank you for watching",
    "subtitles by",
)


def ensure_cuda_libs() -> None:
    """pip ile kurulan nvidia-cublas/cudnn kütüphanelerini LD_LIBRARY_PATH'e ekler.

    dlopen, LD_LIBRARY_PATH'i süreç başlarken okuduğu için gerekirse süreci
    aynı argümanlarla bir kez yeniden başlatır (main.py'nin en başında çağrılmalı).
    """
    if os.environ.get("_VA_REEXEC"):
        return
    try:
        import nvidia  # namespace paketi
        roots = list(nvidia.__path__)
    except Exception:
        return
    libdirs = []
    for root in roots:
        libdirs += sorted(glob.glob(os.path.join(root, "*", "lib")))
    if not libdirs:
        return
    env = os.environ.copy()
    old = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = ":".join(libdirs + ([old] if old else []))
    env["_VA_REEXEC"] = "1"
    os.execve(sys.executable, [sys.executable] + sys.argv, env)


class SpeechToText:
    def __init__(self, model_size: str = WHISPER_MODEL):
        from faster_whisper import WhisperModel  # tembel import (bkz. ensure_cuda_libs)

        self.device = INPUT_DEVICE
        self.model = self._load_model(WhisperModel, model_size)
        self.threshold = self._calibrate()

    # ---------------------------------------------------------------- model
    def _load_model(self, WhisperModel, size):
        try:
            print(f"[STT] faster-whisper '{size}' CUDA (float16) yükleniyor...")
            model = WhisperModel(size, device="cuda", compute_type="float16")
            # CUDA/cuDNN sorunları genelde ilk çalıştırmada ortaya çıkar -> ısınma
            segs, _ = model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language=LANG)
            list(segs)
            print("[STT] CUDA hazır.")
            return model
        except Exception as e:
            print(f"[STT] CUDA başlatılamadı ({e}). CPU (int8) kullanılacak.")
            return WhisperModel(size, device="cpu", compute_type="int8")

    # ------------------------------------------------------------ kalibrasyon
    def _calibrate(self) -> float:
        env = os.getenv("VAD_THRESHOLD")
        if env:
            return float(env)
        print("[STT] Ortam gürültüsü ölçülüyor (1 sn sessiz kal)...")
        rec = sd.rec(SAMPLE_RATE, samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=self.device)
        sd.wait()
        block = int(SAMPLE_RATE * BLOCK_SEC)
        x = rec[:, 0]
        n = len(x) // block
        rms = np.sqrt(np.mean(x[: n * block].reshape(n, block) ** 2, axis=1))
        rms = rms[10:]  # ilk 0.3 sn'deki mikrofon açılış çıtırtısını at
        thr = min(max(0.012, float(np.median(rms)) * 3.0), 0.05)
        print(f"[STT] Ses eşiği: {thr:.4f}")
        return thr

    # ------------------------------------------------------------------ kayıt
    def record(self, wait_timeout=None, silence_sec=1.0, max_sec=20.0):
        """Konuşma başlayana kadar bekler, sessizlik olunca durur. float32 numpy dizisi döner."""
        q: "queue.Queue[np.ndarray]" = queue.Queue()
        block = int(SAMPLE_RATE * BLOCK_SEC)

        def callback(indata, frames, t, status):
            q.put(indata[:, 0].copy())

        preroll = deque(maxlen=int(0.4 / BLOCK_SEC))  # konuşma öncesi 0.4 sn'yi de al
        chunks, speaking = [], False
        speech_blocks = silent_blocks = 0
        max_silent = int(silence_sec / BLOCK_SEC)
        start = time.monotonic()

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=block, device=self.device, callback=callback):
            while True:
                if not speaking and wait_timeout and time.monotonic() - start > wait_timeout:
                    return None
                try:
                    data = q.get(timeout=0.5)
                except queue.Empty:
                    continue
                rms = float(np.sqrt(np.mean(data ** 2)))
                if not speaking:
                    preroll.append(data)
                    if rms > self.threshold:
                        speaking = True
                        chunks = list(preroll)
                        speech_blocks = 1
                else:
                    chunks.append(data)
                    if rms > self.threshold:
                        speech_blocks += 1
                        silent_blocks = 0
                    else:
                        silent_blocks += 1
                    if silent_blocks >= max_silent or len(chunks) * BLOCK_SEC > max_sec:
                        break

        if speech_blocks * BLOCK_SEC < 0.3:  # kısa tıkırtı/gürültü
            return None
        return np.concatenate(chunks)

    # ---------------------------------------------------------------- yazıya çevir
    def transcribe(self, audio: np.ndarray) -> str:
        segments, _ = self.model.transcribe(
            audio,
            language=LANG,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        low = text.lower()
        if len(text) < 2 or any(h in low for h in HALLUCINATIONS):
            return ""
        return text

    def listen_and_transcribe(self, wait_timeout=None) -> str:
        audio = self.record(wait_timeout=wait_timeout)
        if audio is None:
            return ""
        return self.transcribe(audio)
