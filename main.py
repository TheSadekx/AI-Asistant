"""main.py — Yerel sesli asistan: dinle -> anla/işlem yap -> konuş. (ASSISTANT_LANG=en|tr)"""
from stt import ensure_cuda_libs

ensure_cuda_libs()  # cuBLAS/cuDNN yollarını ayarlar (gerekirse süreci bir kez yeniden başlatır)

import re
import time

from agent import LANG, Agent, lower
from stt import SpeechToText
from tts import TextToSpeech

TEXTS = {
    "en": {
        "hello": "Hello, I'm ready. I'm listening.",
        "bye": "Goodbye!",
        "yes_no": " Yes or no?",
        "exit": ("goodbye", "good bye", "exit assistant", "quit assistant", "close assistant",
                 "close the program", "close program", "exit program", "quit program",
                 "shut yourself down", "turn yourself off", "stop the assistant"),
        "yes": ("yes", "yeah", "yep", "sure", "ok", "okay", "go ahead", "do it", "confirm"),
        "no": ("no", "nope", "don't", "do not", "cancel", "stop", "never mind"),
    },
    "tr": {
        "hello": "Merhaba, ben hazırım. Seni dinliyorum.",
        "bye": "Görüşürüz!",
        "yes_no": " Evet ya da hayır?",
        "exit": ("görüşürüz", "hoşça kal", "kendini kapat", "programı kapat", "çıkış yap"),
        "yes": ("evet", "onaylıyorum", "onay", "tamam", "olur", "çalıştır"),
        "no": ("hayır", "yapma", "iptal", "olmaz", "vazgeç", "dur"),
    },
}
T = TEXTS.get(LANG, TEXTS["en"])
EXIT_PHRASES = TEXTS["en"]["exit"] + TEXTS["tr"]["exit"]  # kapatma cümleleri her iki dilde de geçerli


def has_word(text: str, words) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


def main() -> None:
    tts = TextToSpeech()
    stt = SpeechToText()

    def confirm(question: str) -> bool:
        tts.speak(question + T["yes_no"])
        time.sleep(0.3)
        answer = lower(stt.listen_and_transcribe(wait_timeout=8))
        print(f"Onay cevabı: {answer!r}")
        if not answer or has_word(answer, T["no"]):
            return False
        return has_word(answer, T["yes"])

    agent = Agent(confirm=confirm)
    try:
        agent.check_ready()
    except RuntimeError as e:
        print(f"❌ {e}")
        return

    tts.speak(T["hello"])
    try:
        while True:
            print("\n🎤 Listening...")
            text = stt.listen_and_transcribe()
            if not text:
                continue
            print(f"👤 {text}")

            if any(p in lower(text) for p in EXIT_PHRASES):
                tts.speak(T["bye"])
                break

            reply = agent.ask(text)
            tts.speak(reply)
            time.sleep(0.3)  # kendi sesimizi mikrofondan duymayalım
    except KeyboardInterrupt:
        print("\nÇıkılıyor...")


if __name__ == "__main__":
    main()
