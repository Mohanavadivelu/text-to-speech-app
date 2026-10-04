"""Text helpers: cleanup, file loading, pronunciations and duration estimates."""
import json
import logging
import os
import re
import unicodedata

from core import paths

log = logging.getLogger(__name__)

PRONUNCIATIONS_PATH = paths.PRONUNCIATIONS_PATH
DRAFT_PATH = paths.DRAFT_PATH

OPEN_FILETYPES = [
    ("Text documents", "*.txt *.md *.docx *.pdf"),
    ("Plain text", "*.txt *.md"),
    ("Word document", "*.docx"),
    ("PDF", "*.pdf"),
    ("All files", "*.*"),
]

# ── Duration estimate ────────────────────────────────────────────────────────
# Characters of speech per second at speed 1.0, measured with Kokoro-82M.
_CHARS_PER_SEC = {"a": 14.0, "b": 14.0, "h": 12.0, "f": 22.0, "e": 18.0, "i": 18.0, "p": 18.0}


def estimate_seconds(text: str, lang_code: str = "a", speed: float = 1.0) -> float:
    if not text.strip():
        return 0.0
    rate = _CHARS_PER_SEC.get(lang_code, 15.0) * max(0.1, speed)
    return len(text) / rate


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def count_words(text: str) -> int:
    return len(text.split())


# ── Clean text ───────────────────────────────────────────────────────────────
_CHAR_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "′": "'", "″": '"', "«": '"', "»": '"',
    "–": " - ", "−": "-", "‐": "-", "‑": "-",
    " ": " ", " ": " ", " ": " ", " ": " ", "　": " ",
    "​": "", "‌": "", "‍": "", "﻿": "", "­": "",
    "…": "...", "•": "", "●": "", "▪": "", "‣": "",
}
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# [text](url) -> text, but keep Kokoro pronunciation markup [word](/phonemes/)
_MD_LINK = re.compile(r"\[([^\]]+)\]\((?!/)[^)]*\)")
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_MD_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.MULTILINE)
_MD_QUOTE = re.compile(r"^[ \t]*>+[ \t]?", re.MULTILINE)
_MD_BULLET = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+", re.MULTILINE)
_MD_RULE = re.compile(r"^[ \t]*(?:[-*_][ \t]*){3,}$", re.MULTILINE)
_MD_EMPHASIS = re.compile(r"(\*\*|__|\*|_|~~|`+)(?=\S)(.+?)(?<=\S)\1")
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_SENTENCE_END = (".", "!", "?", ":", ";", "\"", "'", ")", "।", "॥")


def clean_text(text: str) -> str:
    """Tidy pasted text so the voice reads it smoothly.

    Normalises quotes, dashes and invisible characters; removes links, e-mail
    addresses and markdown symbols; re-joins lines broken mid-sentence (common
    in PDFs); collapses extra spaces. Paragraph breaks are kept.
    """
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = "".join(_CHAR_MAP.get(ch, ch) for ch in text)

    text = _MD_IMAGE.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    text = _EMAIL.sub("", text)
    text = _MD_RULE.sub("", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_QUOTE.sub("", text)
    text = _MD_BULLET.sub("", text)
    text = _MD_EMPHASIS.sub(r"\2", text)

    text = _HYPHEN_BREAK.sub(r"\1\2", text)

    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in block.split("\n")]
        lines = [ln for ln in lines if ln]
        if not lines:
            continue
        merged = lines[0]
        for ln in lines[1:]:
            # A line that ends a sentence, or a short heading-like line, stays on its own
            last = merged.rsplit("\n", 1)[-1]
            if last.endswith(_SENTENCE_END) or len(last) < 40:
                merged += "\n" + ln
            else:
                merged += " " + ln
        paragraphs.append(merged)
    text = "\n\n".join(paragraphs)

    text = re.sub(r" +([,.!?;:])", r"\1", text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# ── File loading ─────────────────────────────────────────────────────────────
MAX_FILE_CHARS = 2_000_000


def load_text_file(path: str) -> tuple[str, bool]:
    """Read *path* and return (text, was_cleaned).

    PDFs are cleaned automatically because their text is always hard-wrapped.
    Raises ValueError with a readable message on failure.
    """
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".docx":
            import docx
            doc = docx.Document(path)
            text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
            return text, False
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(path)
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:
                    raise ValueError("This PDF is password-protected.")
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
            if not text.strip():
                raise ValueError("This PDF has no selectable text (it may be scanned images).")
            return clean_text(text), True
        with open(path, "rb") as f:
            raw = f.read(MAX_FILE_CHARS * 4 + 1)
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            return raw.decode("utf-16", errors="replace"), False
        try:
            return raw.decode("utf-8-sig"), False
        except UnicodeDecodeError:
            return raw.decode("cp1252", errors="replace"), False
    except ValueError:
        raise
    except Exception as exc:
        log.exception("Could not open %s", path)
        kind = {".docx": "Word document", ".pdf": "PDF"}.get(ext)
        if kind:
            raise ValueError(f"This {kind} is damaged or not a real {ext} file.") from exc
        raise ValueError(f"Could not open file: {exc}") from exc


# ── Draft ────────────────────────────────────────────────────────────────────
def load_draft() -> str:
    try:
        with open(DRAFT_PATH, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except Exception as exc:
        log.warning("Could not read draft: %s", exc)
        return ""


def save_draft(text: str):
    try:
        if not text.strip():
            if os.path.exists(DRAFT_PATH):
                os.remove(DRAFT_PATH)
            return
        os.makedirs(os.path.dirname(DRAFT_PATH), exist_ok=True)
        tmp = DRAFT_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, DRAFT_PATH)
    except Exception as exc:
        log.warning("Could not save draft: %s", exc)


# ── Pronunciations ───────────────────────────────────────────────────────────
def load_pronunciations() -> list[dict]:
    """Return [{"word": str, "say": str}, ...]. Never raises."""
    try:
        with open(PRONUNCIATIONS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return [{"word": str(e["word"]), "say": str(e["say"])} for e in data
                if isinstance(e, dict) and str(e.get("word", "")).strip()
                and str(e.get("say", "")).strip()]
    except FileNotFoundError:
        return []
    except Exception as exc:
        log.warning("Ignoring unreadable pronunciations file: %s", exc)
        return []


def save_pronunciations(entries: list[dict]):
    try:
        os.makedirs(os.path.dirname(PRONUNCIATIONS_PATH), exist_ok=True)
        tmp = PRONUNCIATIONS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        os.replace(tmp, PRONUNCIATIONS_PATH)
    except Exception as exc:
        log.warning("Could not save pronunciations: %s", exc)


def apply_pronunciations(text: str, entries: list[dict], lang_code: str = "a") -> str:
    """Replace whole words (case-insensitive) with how they should be said.

    A "say" value wrapped in slashes, like /kˈOkəɹO/, is phonemes; it becomes
    Kokoro's [word](/phonemes/) markup, which only English voices understand.
    For other languages the word is left unchanged.
    """
    if not entries:
        return text
    # Longest words first so "New York City" wins over "New York"
    for entry in sorted(entries, key=lambda e: -len(e["word"])):
        word, say = entry["word"].strip(), entry["say"].strip()
        is_phonemes = len(say) > 2 and say.startswith("/") and say.endswith("/")
        if is_phonemes and lang_code not in ("a", "b"):
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(word)}(?!\w)", re.IGNORECASE)
        if is_phonemes:
            text = pattern.sub(lambda m: f"[{m.group(0)}]({say})", text)
        else:
            text = pattern.sub(lambda _m: say, text)
    return text
