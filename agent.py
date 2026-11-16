"""agent.py — Ollama (qwen2.5:7b) ile function calling yapan ajan.

Araçlar: uygulama açma, URL açma, komut çalıştırma (güvenlik kontrollü), ses seviyesi, tarih/saat.
Dil: ASSISTANT_LANG=en (varsayılan) veya tr
"""
import datetime
import os
import re
import shlex
import shutil
import subprocess
from typing import Callable, Optional

import ollama

MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
LANG = os.getenv("ASSISTANT_LANG", "en").lower()
MAX_STEPS = 5       # bir istekte en fazla kaç araç turu
HISTORY_LIMIT = 20  # hafızada tutulan mesaj sayısı

SYSTEM_PROMPTS = {
    "en": """You are a voice assistant running locally on a Fedora Linux computer.
Rules:
- Your answers are read aloud: keep them short and natural, at most 2-3 sentences. No markdown, bullet points, emoji or code blocks.
- If the user wants to open an app or website, run a command, change the volume, or know the date and time, call the matching tool, then briefly summarize the result.
- Answer chat and knowledge questions directly, without tools.
- Never make things up; say so when you don't know.""",
    "tr": """Sen Türkçe konuşan, bilgisayarda yerel çalışan bir sesli asistansın. Sistem: Fedora Linux.
Kurallar:
- Cevapların sesli okunacak: kısa ve doğal ol, en fazla 2-3 cümle. Markdown, madde işareti, emoji ve kod bloğu kullanma.
- Kullanıcı bir uygulama/site açmak, komut çalıştırmak, ses ayarlamak veya saati öğrenmek isterse ilgili aracı çağır, sonra sonucu kısaca özetle.
- Sohbet ve bilgi sorularına araç kullanmadan doğrudan cevap ver.
- Bilmediğin şeyi uydurma; bilmediğini söyle.""",
}
SYSTEM_PROMPT = SYSTEM_PROMPTS.get(LANG, SYSTEM_PROMPTS["en"])


def tr_lower(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def lower(s: str) -> str:
    """Seçili dile uygun küçük harfe çevirme."""
    return tr_lower(s) if LANG == "tr" else s.lower()


# ------------------------------------------------------------------ araçlar
APP_ALIASES = {
    # İngilizce ve Türkçe adlar birlikte tanınır
    "browser": ["firefox", "google-chrome-stable", "google-chrome", "chromium-browser", "chromium"],
    "tarayıcı": ["firefox", "google-chrome-stable", "google-chrome", "chromium-browser", "chromium"],
    "firefox": ["firefox"],
    "chrome": ["google-chrome-stable", "google-chrome", "chromium-browser", "chromium"],
    "terminal": ["ptyxis", "gnome-terminal", "konsole", "xterm"],
    "files": ["nautilus", "dolphin", "thunar"],
    "file manager": ["nautilus", "dolphin", "thunar"],
    "dosya": ["nautilus", "dolphin", "thunar"],
    "calculator": ["gnome-calculator", "kcalc"],
    "hesap makinesi": ["gnome-calculator", "kcalc"],
    "text editor": ["gnome-text-editor", "gedit", "kate"],
    "notepad": ["gnome-text-editor", "gedit", "kate"],
    "metin editörü": ["gnome-text-editor", "gedit", "kate"],
    "settings": ["gnome-control-center", "systemsettings"],
    "ayarlar": ["gnome-control-center", "systemsettings"],
    "system monitor": ["gnome-system-monitor", "plasma-systemmonitor"],
    "task manager": ["gnome-system-monitor", "plasma-systemmonitor"],
    "vs code": ["code", "codium"],
    "vscode": ["code", "codium"],
    "visual studio": ["code", "codium"],
    "spotify": ["spotify", "flatpak run com.spotify.Client"],
    "discord": ["discord", "flatpak run com.discordapp.Discord"],
    "steam": ["steam"],
    "vlc": ["vlc"],
    "calendar": ["gnome-calendar", "korganizer"],
    "camera": ["snapshot", "cheese"],
}


def _launch(parts: list[str]) -> None:
    subprocess.Popen(parts, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def open_application(name: str) -> str:
    key = lower(name).strip()
    key = re.sub(r"\b(the|app|application|program|uygulaması|uygulamasını|programı|programını)\b", "", key)
    key = re.sub(r"\s+", " ", key).strip()
    candidates: list[str] = []
    for alias, cmds in APP_ALIASES.items():
        if key == alias or alias in key:
            candidates += cmds
    candidates.append(key.replace(" ", "-"))  # doğrudan komut adı dene

    for cmd in candidates:
        parts = shlex.split(cmd)
        if parts and shutil.which(parts[0]):
            try:
                _launch(parts)
                return f"{name} was opened."
            except Exception as e:
                return f"Could not open {name}: {e}"
    if shutil.which("gtk-launch"):  # .desktop dosyası adıyla son deneme
        r = subprocess.run(["gtk-launch", key.replace(" ", "-")], capture_output=True)
        if r.returncode == 0:
            return f"{name} was opened."
    return f"No application called {name} was found."


def open_url(url: str) -> str:
    if not re.match(r"^https?://", url):
        url = "https://" + url
    _launch(["xdg-open", url])
    return f"{url} was opened in the default browser."


SAFE_COMMANDS = {"ls", "pwd", "date", "uptime", "whoami", "uname", "df", "free", "nvidia-smi",
                 "hostname", "lscpu", "lsblk", "cal", "echo", "ps", "sensors"}
BLOCKED_COMMANDS = {"sudo", "su", "dd", "fdisk", "parted", "wipefs", "shred", "mkfs", "chown", "chmod"}


def run_command(command: str, confirm: Optional[Callable[[str], bool]] = None) -> str:
    """Kabuk (shell) kullanmadan komut çalıştırır; boru/yönlendirme/zincirleme desteklenmez."""
    try:
        args = shlex.split(command)
    except ValueError as e:
        return f"Could not parse the command: {e}"
    if not args:
        return "Empty command."
    prog = os.path.basename(args[0])
    if prog in BLOCKED_COMMANDS or prog.startswith("mkfs") or (
        prog == "rm" and any(a.startswith("-") and ("r" in a or "R" in a) for a in args[1:])
    ):
        return f"The command '{prog}' is blocked for safety reasons."
    if prog not in SAFE_COMMANDS:
        question = (f"Şu komutu çalıştırayım mı: {command}" if LANG == "tr"
                    else f"Should I run this command: {command}")
        if confirm is None or not confirm(question):
            return "The user did not confirm, so the command was not run."
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=20, cwd=os.path.expanduser("~"))
    except FileNotFoundError:
        return f"Command '{prog}' not found."
    except subprocess.TimeoutExpired:
        return "The command did not finish within 20 seconds and was stopped."
    out = (r.stdout + r.stderr).strip()
    return f"Exit code {r.returncode}. Output: {out[:1200] or '(empty)'}"


def set_volume(percent: int) -> str:
    percent = max(0, min(100, int(percent)))
    if shutil.which("wpctl"):
        cmd = ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{percent}%"]
    elif shutil.which("pactl"):
        cmd = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"]
    else:
        return "Neither wpctl nor pactl was found."
    r = subprocess.run(cmd, capture_output=True, text=True)
    return f"Volume set to {percent} percent." if r.returncode == 0 else f"Could not set volume: {r.stderr.strip()}"


def get_datetime() -> str:
    n = datetime.datetime.now()
    return n.strftime("%A, %B %d, %Y, %H:%M")


TOOLS = [
    {"type": "function", "function": {
        "name": "open_application",
        "description": "Opens an application on the computer (e.g. firefox, terminal, calculator, spotify, vs code).",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Name of the application"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "open_url",
        "description": "Opens a website in the default browser.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "E.g. https://youtube.com"}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "Runs a single Linux command and returns its output (no pipes or redirects). E.g. 'df -h', 'nvidia-smi'.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "One command with its arguments"}}, "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "set_volume",
        "description": "Sets the system volume between 0 and 100 percent.",
        "parameters": {"type": "object", "properties": {
            "percent": {"type": "integer", "description": "Percentage from 0 to 100"}}, "required": ["percent"]}}},
    {"type": "function", "function": {
        "name": "get_datetime",
        "description": "Returns the current date and time.",
        "parameters": {"type": "object", "properties": {}}}},
]


# --------------------------------------------------------------------- ajan
class Agent:
    def __init__(self, confirm: Optional[Callable[[str], bool]] = None):
        self.client = ollama.Client()
        self.confirm = confirm
        self.messages: list = []
        self.tools = {
            "open_application": open_application,
            "open_url": open_url,
            "run_command": lambda command: run_command(command, self.confirm),
            "set_volume": set_volume,
            "get_datetime": get_datetime,
        }

    def check_ready(self) -> None:
        """Ollama çalışıyor mu ve model inmiş mi? Değilse anlaşılır hata ver."""
        try:
            names = [m.model for m in self.client.list().models]
        except Exception as e:
            raise RuntimeError(f"Ollama'ya bağlanılamadı ({e}). 'sudo systemctl start ollama' dene.")
        if not any(n == MODEL or n == MODEL + ":latest" for n in names):
            raise RuntimeError(f"'{MODEL}' modeli yok. Şunu çalıştır: ollama pull {MODEL}")
        self.client.chat(model=MODEL, messages=[{"role": "user", "content": "hi"}],
                         keep_alive="30m", options={"num_predict": 1})  # modeli GPU'ya yükle

    @staticmethod
    def _role(m) -> str:
        return m["role"] if isinstance(m, dict) else m.role

    def _trim(self) -> None:
        if len(self.messages) <= HISTORY_LIMIT:
            return
        cut = len(self.messages) - HISTORY_LIMIT
        while cut < len(self.messages) and self._role(self.messages[cut]) != "user":
            cut += 1  # araç yanıtıyla başlayan yetim mesaj bırakma
        self.messages = self.messages[cut:]

    def ask(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        self._trim()

        for _ in range(MAX_STEPS):
            resp = self.client.chat(
                model=MODEL,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + self.messages,
                tools=TOOLS,
                keep_alive="30m",
                options={"temperature": 0.3},
            )
            msg = resp.message
            self.messages.append(msg)

            if not msg.tool_calls:
                return (msg.content or "").strip() or ("Tamamdır." if LANG == "tr" else "Done.")

            for call in msg.tool_calls:
                name, args = call.function.name, dict(call.function.arguments or {})
                print(f"🛠  {name}({args})")
                fn = self.tools.get(name)
                try:
                    result = fn(**args) if fn else f"Unknown tool: {name}"
                except Exception as e:
                    result = f"Tool error: {e}"
                print(f"   ↳ {result}")
                self.messages.append({"role": "tool", "content": str(result), "tool_name": name})

        return ("İşlemi tamamlayamadım, tekrar dener misin?" if LANG == "tr"
                else "I couldn't finish that, could you try again?")
