#!/usr/bin/env python3
"""
Amharic transliteration for the Telegram notifications.

Product names and delivery names are written in Latin script, but the store
team and the admin read them in Amharic (Geez). This service is the single
place that performs that conversion.

Resolution order for every name:

    1. a correction saved by the user  (database/amharic_overrides.json)
    2. the shipped seed dictionary     (services/data/amharic_seed.json)
    3. English-aware rewrite rules + the ``fidel`` syllable engine
    4. plain ``fidel`` output, as a last resort

The seed dictionary was generated with knowledge of English spelling and of
how Ethiopian shops write these names, so it fixes words such as ``titanic``
-> ቲታኒክ and ``storage`` -> ስቶራጅ that a letter-by-letter transliterator turns
into ቲታኒጭ / ስቶራገ.

Nothing in here ever raises: on any failure the original text is returned so
that a notification is always sent.
"""

import json
import logging
import os
import re
import threading
import time

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional `fidel` dependency
#
# `fidel` is the syllable engine (Latin chunk -> Geez character). It is pinned
# in requirements.txt, but the app must keep working on a machine where it is
# missing, so a small built-in table is used as a fallback.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - depends on the environment
    from fidel import Transliterate as _FidelTransliterate
except Exception:  # pragma: no cover
    _FidelTransliterate = None


# ---------------------------------------------------------------------------
# Built-in syllable table (fallback for `fidel`)
# ---------------------------------------------------------------------------
_CONSONANT_ROWS = [
    ("l", "ለሉሊላሌልሎሏ"),
    ("m", "መሙሚማሜምሞሟ"),
    ("r", "ረሩሪራሬርሮሯ"),
    ("s", "ሰሱሲሳሴስሶሷ"),
    ("sh", "ሸሹሺሻሼሽሾሿ"),
    ("q", "ቀቁቂቃቄቅቆቋ"),
    ("b", "በቡቢባቤብቦቧ"),
    ("v", "ቨቩቪቫቬቭቮቯ"),
    ("t", "ተቱቲታቴትቶቷ"),
    ("ch", "ቸቹቺቻቼችቾ "),
    ("y", "የዩዪያዬይዮ "),
    ("n", "ነኑኒናኔንኖኗ"),
    ("gn", "ኘኙኚኛኜኝኞኟ"),
    ("k", "ከኩኪካኬክኮኳ"),
    ("w", "ወዉዊዋዌውዎ "),
    ("z", "ዘዙዚዛዜዝዞዟ"),
    ("zh", "ዠዡዢዣዤዥዦዧ"),
    ("d", "ደዱዲዳዴድዶዷ"),
    ("j", "ጀጁጂጃጄጅጆ "),
    ("g", "ገጉጊጋጌግጎጓ"),
    ("x", "ጰጱጲጳጴጵጶጷ"),
    ("c", "ጨጩጪጫጬጭጮጯ"),
    ("ts", "ጸጹጺጻጼጽጾ "),
    ("ph", "ጰጱጲጳጴጵጶጷ"),
    ("f", "ፈፉፊፋፌፍፎፏ"),
    ("p", "ፐፑፒፓፔፕፖፗ"),
]
_VOWELS = ["e", "u", "i", "a", "ie", "", "o", "ua"]
_A_VOWELS = ["a", "u", "i", "", "ie", "e", "o", "ua"]
_A_ROW = "አኡኢ ኤእኦኧ"
_H_VOWELS = ["a", "u", "i", "", "e", "", "o", "ua"]
_H_ROW = "ሀሁሂ ሄህሆኋ"


def _build_syllables():
    """Build a ``latin chunk -> geez char`` table (same scheme as `fidel`)."""
    table = {}
    for consonant, row in _CONSONANT_ROWS:
        for index, vowel in enumerate(_VOWELS):
            char = row[index]
            if char.strip():
                table[consonant + vowel] = char
    for vowel, char in zip(_A_VOWELS, _A_ROW):
        if vowel:
            table[vowel] = char
    for vowel, char in zip(_H_VOWELS, _H_ROW):
        if vowel:
            table["h" + vowel] = char
    return table


_SYLLABLES = _build_syllables()
_SYLLABLE_KEYS = sorted(_SYLLABLES, key=len, reverse=True)
_SINGLE_CONSONANTS = {c: row[5] for c, row in _CONSONANT_ROWS if row[5].strip()}


def _fallback_transliterate(text: str) -> str:
    """Minimal stand-in for `fidel`, used only when it is not installed."""
    out = []
    index = 0
    lowered = text.lower()
    while index < len(lowered):
        matched = False
        for key in _SYLLABLE_KEYS:
            if lowered.startswith(key, index):
                out.append(_SYLLABLES[key])
                index += len(key)
                matched = True
                break
        if matched:
            continue
        char = lowered[index]
        if char in _SINGLE_CONSONANTS:
            out.append(_SINGLE_CONSONANTS[char])
        else:
            out.append(text[index])
        index += 1
    return "".join(out)


def transliterate_phonetic(text: str) -> str:
    """Convert romanized Amharic ("storaj", "kuter") into Geez characters."""
    if not text:
        return text
    if _FidelTransliterate is not None:
        try:
            result = _FidelTransliterate(text).transliterate()
            if result:
                return result
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("fidel failed for %r: %s", text, exc)
    return _fallback_transliterate(text)


# ---------------------------------------------------------------------------
# English spelling -> Amharic-sounding romanization
#
# These rules only run on words that look English. Romanized Amharic words
# (which `fidel` already handles well) are never touched by them.
# ---------------------------------------------------------------------------
_HARD_G = {
    "get", "gets", "getting", "give", "gives", "given", "girl", "gift", "gifts",
    "gear", "gears", "begin", "begins", "tiger", "target", "garden", "gallon",
    "anger", "finger", "hunger", "gather", "germ", "ger", "gered",
}
_WORD_ENDINGS = [
    ("tion", "shn"),
    ("sion", "shn"),
    ("tch", "ch"),
    ("dge", "j"),
    ("ck", "k"),
    ("ph", "f"),
    ("th", "t"),
    ("wh", "w"),
    ("x", "ks"),
]
_VOWEL_DIGRAPHS = [
    ("ee", "i"),
    ("ea", "i"),
    ("ie", "ai"),
    ("oo", "u"),
    ("ou", "u"),
    ("ow", "o"),
    ("oa", "o"),
    ("ui", "u"),
    ("ue", "u"),
    ("ay", "ai"),
    ("ai", "ai"),
    ("ey", "i"),
]


def _replace_once(word: str, old: str, new: str) -> str:
    return word.replace(old, new)


def english_to_phonetic(word: str) -> str:
    """
    Rewrite an English word the way it sounds, so that `fidel` can turn it
    into Amharic syllables: ``titanic`` -> ``titanik``, ``storage`` -> ``storaj``.
    """
    if not word:
        return word

    word = word.lower()

    # Initial silent consonants.
    if word.startswith("kn") or word.startswith("wr") or word.startswith("gn"):
        word = word[1:]
    elif word.startswith("ps"):
        word = word[1:]

    # Consonant digraphs / endings.
    for old, new in _WORD_ENDINGS:
        if old in word:
            word = _replace_once(word, old, new)

    # Soft endings decided by the final "e": storage -> storaj, office -> ofis.
    word = re.sub(r"ge$", "j", word)
    word = re.sub(r"ce$", "s", word)
    word = re.sub(r"gue$", "g", word)

    # Hard / soft c and g.
    word = re.sub(r"c(?=[eiy])", "s", word)
    word = re.sub(r"c(?!h)", "k", word)
    if word not in _HARD_G:
        word = re.sub(r"g(?=[eiy])", "j", word)

    # Magic-e endings: name -> niem, ice -> ais, note -> not, cube -> kub.
    word = re.sub(r"a([bcdfgklmnprstvz])e$", r"ie\1", word)
    word = re.sub(r"i([bcdfgklmnprstvz])e$", r"ai\1", word)
    word = re.sub(r"o([bcdfgklmnprstvz])e$", r"o\1", word)
    word = re.sub(r"u([bcdfgklmnprstvz])e$", r"u\1", word)
    word = re.sub(r"e([bcdfgklmnprstvz])e$", r"i\1", word)

    # Vowel digraphs.
    for old, new in _VOWEL_DIGRAPHS:
        if old in word:
            word = _replace_once(word, old, new)

    # "gh" is usually silent (light -> lait) and "ght" -> t (bright -> brait).
    word = re.sub(r"ght", "t", word)
    word = re.sub(r"(?<=[aeiou])gh", "", word)
    word = word.replace("gh", "g")

    # Silent final "e".
    word = re.sub(r"(?<=[bcdfgklmnprstvz])e$", "", word)

    # Doubled consonants collapse: coffee -> kofi, glass -> glas.
    word = re.sub(r"([bcdfgklmnprstvz])\1", r"\1", word)

    # Final "-ed" -> d, "-le" -> l (bottle -> botl).
    word = re.sub(r"ed$", "d", word) if len(word) > 4 else word
    word = re.sub(r"le$", "l", word) if len(word) > 3 else word

    return word


# ---------------------------------------------------------------------------
# Keys and tokenizing
# ---------------------------------------------------------------------------
_WORD_CHUNK = re.compile(r"[A-Za-z]+(?:[/&.'\-][A-Za-z]+)*")
# Codes such as M3, ZB47, S001, EP100 stay exactly as they are written.
_TOKEN = re.compile(
    r"[A-Za-z\d]*\d[A-Za-z\d]*|[A-Za-z]+(?:[/&.'\-][A-Za-z]+)*|[^A-Za-z\d]+"
)
_CONNECTOR = re.compile(r"[/&.'\-]")
_ENGLISH_HINTS = re.compile(
    r"ck|ph|th|wh|x|tion|dge|ee|ea|ou|ow|ai|ay|ui|oo|c(?!h)|qu(?=[aeiou])"
)
_SOFT_G = re.compile(r"g[eiy]")


def normalize_key(text: str) -> str:
    """Key used for dictionary lookups: trimmed, single-spaced, upper case."""
    return re.sub(r"\s+", " ", (text or "").strip()).upper()


def _looks_english(word: str, english_words: set) -> bool:
    upper = word.upper()
    if upper in english_words:
        return True
    lowered = word.lower()
    if _ENGLISH_HINTS.search(lowered):
        return True
    # A soft g is an English signal only for a word the dictionary does not
    # know: Amharic vocabulary ("EGER", "GENDA") is always in the seed.
    return bool(_SOFT_G.search(lowered))


def _translate_word(word: str, entries: dict, english_words: set) -> str:
    """Convert a single Latin word into Amharic."""
    upper = word.upper()
    if upper in entries:
        return entries[upper]

    phonetic = word.lower()
    if _looks_english(word, english_words):
        phonetic = english_to_phonetic(phonetic)
    converted = transliterate_phonetic(phonetic)
    return converted or word


def _translate_chunk(chunk: str, entries: dict, english_words: set) -> str:
    """Convert one word chunk, keeping internal separators (M/CHA, B/DAR)."""
    upper = chunk.upper()
    if upper in entries:
        return entries[upper]
    if _CONNECTOR.search(chunk):
        parts = re.split(r"([/&.'\-])", chunk)
        return "".join(
            part if _CONNECTOR.fullmatch(part) else _translate_word(part, entries, english_words)
            for part in parts
        )
    return _translate_word(chunk, entries, english_words)


# ---------------------------------------------------------------------------
# Seed / corrections storage
# ---------------------------------------------------------------------------
def _seed_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "amharic_seed.json")


class AmharicService:
    """
    Converts Latin-script names into Amharic and remembers user corrections.

    ``AmharicService()`` is a singleton; every call site shares one dictionary
    in memory.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._lock = threading.RLock()
        self._entries = {}          # user corrections: KEY -> Amharic
        self._seed_entries = {}     # shipped seed: KEY -> Amharic
        self._seed_english = set()  # words that should follow the English rules
        self._seed_review = set()   # seed keys the user should double-check
        self._overrides_path = ""
        self._overrides_mtime = 0.0
        self._load_seed()
        self._load_overrides()

    # ------------------------------------------------------------------ seed
    def _load_seed(self):
        try:
            path = _seed_path()
            if not os.path.exists(path):
                logger.warning("Amharic seed dictionary not found at %s", path)
                return
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self._seed_entries = {
                normalize_key(key): value
                for key, value in (data.get("entries") or {}).items()
                if value
            }
            self._seed_english = {w.upper() for w in (data.get("english") or [])}
            self._seed_review = {normalize_key(k) for k in (data.get("review") or [])}
            logger.info("Amharic seed dictionary loaded: %d entries", len(self._seed_entries))
        except Exception as exc:
            logger.error("Failed to load Amharic seed dictionary: %s", exc)
            self._seed_entries = {}
            self._seed_english = set()
            self._seed_review = set()

    # ----------------------------------------------------- user corrections
    def _overrides_file(self) -> str:
        if self._overrides_path:
            return self._overrides_path
        try:
            from utils import get_json_path

            self._overrides_path = get_json_path("amharic_overrides.json")
        except Exception:
            self._overrides_path = os.path.join(os.getcwd(), "amharic_overrides.json")
        return self._overrides_path

    def _load_overrides(self):
        """Load corrections from disk (also used to pick up outside edits)."""
        with self._lock:
            path = self._overrides_file()
            try:
                if not os.path.exists(path):
                    self._entries = {}
                    return
                self._overrides_mtime = os.path.getmtime(path)
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                self._entries = {
                    normalize_key(key): value
                    for key, value in (data.get("entries") or {}).items()
                    if value
                }
            except Exception as exc:
                logger.error("Failed to load Amharic corrections: %s", exc)

    def _refresh_overrides(self):
        """Reload the corrections file when it changed on disk."""
        try:
            path = self._overrides_file()
            if not os.path.exists(path):
                return
            mtime = os.path.getmtime(path)
            if mtime > self._overrides_mtime:
                self._load_overrides()
        except Exception:
            pass

    def _save_overrides(self):
        with self._lock:
            path = self._overrides_file()
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                payload = {
                    "version": 1,
                    "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "entries": self._entries,
                }
                temp_path = path + ".tmp"
                with open(temp_path, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                os.replace(temp_path, path)
                self._overrides_mtime = os.path.getmtime(path)
            except Exception as exc:
                logger.error("Failed to save Amharic corrections: %s", exc)

    # ------------------------------------------------------------- public API
    def to_amharic(self, text: str) -> str:
        """Convert a product name or delivery name into Amharic."""
        if not text or not str(text).strip():
            return text
        try:
            self._refresh_overrides()
            original = str(text)
            entries = dict(self._seed_entries)
            entries.update(self._entries)  # user corrections win

            key = normalize_key(original)
            if key in entries:
                return entries[key]

            english_words = self._seed_english
            converted = "".join(
                token if _WORD_CHUNK.fullmatch(token) is None
                else _translate_chunk(token, entries, english_words)
                for token in _TOKEN.findall(original)
            )
            return converted or original
        except Exception as exc:
            logger.error("Amharic conversion failed for %r: %s", text, exc, exc_info=True)
            return text

    def to_amharic_phonetic(self, text: str) -> str:
        """
        Convert romanized Amharic ("storaj", "tena yistilign") without the
        English rewrite rules. This powers the "sounds like" box in the UI.
        """
        if not text or not str(text).strip():
            return text
        try:
            self._refresh_overrides()
            entries = dict(self._seed_entries)
            entries.update(self._entries)
            return "".join(
                token if _WORD_CHUNK.fullmatch(token) is None
                else _translate_chunk(token, entries, set())
                for token in _TOKEN.findall(str(text))
            )
        except Exception as exc:
            logger.error("Phonetic Amharic conversion failed for %r: %s", text, exc)
            return text

    def describe(self, text: str):
        """Return ``(amharic, source)`` where source is custom/seed/rules/none."""
        if not text or not str(text).strip():
            return text, "none"
        key = normalize_key(text)
        self._refresh_overrides()
        if key in self._entries:
            return self._entries[key], "custom"
        if key in self._seed_entries:
            return self._seed_entries[key], "seed"
        return self.to_amharic(text), "rules"

    def suggest(self, text: str):
        """
        Candidate spellings for the correction dialog.

        Returns a list of ``(source, amharic)`` pairs, best first, without
        duplicates: the saved correction, the seed entry, the rule-based
        result, the pure phonetic ("sounds like") result.
        """
        candidates = []
        if not text or not str(text).strip():
            return candidates
        key = normalize_key(text)
        self._refresh_overrides()

        def add(source, value):
            if value and all(value != existing for _, existing in candidates):
                candidates.append((source, value))

        if key in self._entries:
            add("custom", self._entries[key])
        if key in self._seed_entries:
            add("seed", self._seed_entries[key])
        add("rules", self.to_amharic(text))
        add("phonetic", self.to_amharic_phonetic(text))
        # What the app used to send (plain letter-by-letter fidel table).
        cleaned = re.sub(r"\s+", " ", str(text).lower().strip())
        add("old", transliterate_phonetic(cleaned))
        return candidates

    def is_custom(self, text: str) -> bool:
        return normalize_key(text) in self._entries

    def has_seed(self, text: str) -> bool:
        return normalize_key(text) in self._seed_entries

    def needs_review(self, text: str) -> bool:
        key = normalize_key(text)
        if key in self._entries:
            return False
        if key in self._seed_review:
            return True
        return all(token in self._seed_review for token in key.split() if token)

    def set_override(self, original: str, amharic: str):
        """Remember a correction for this name (or for a single word)."""
        key = normalize_key(original)
        if not key or not amharic or not amharic.strip():
            return False
        with self._lock:
            self._entries[key] = amharic.strip()
            self._save_overrides()
        return True

    def remove_override(self, original: str) -> bool:
        key = normalize_key(original)
        with self._lock:
            if key not in self._entries:
                return False
            del self._entries[key]
            self._save_overrides()
        return True

    def all_overrides(self) -> dict:
        self._refresh_overrides()
        return dict(self._entries)

    def reload(self):
        self._load_seed()
        self._load_overrides()

    def stats(self) -> dict:
        return {
            "seed_entries": len(self._seed_entries),
            "seed_english": len(self._seed_english),
            "seed_review": len(self._seed_review),
            "corrections": len(self._entries),
            "fidel_available": _FidelTransliterate is not None,
            "overrides_path": self._overrides_file(),
        }


# Convenience module level helpers used by the UI and the notifications.
def to_amharic(text: str) -> str:
    """Convert a product/delivery name into Amharic (never raises)."""
    try:
        return AmharicService().to_amharic(text)
    except Exception:
        return text


def to_amharic_phonetic(text: str) -> str:
    """Convert a "sounds like" latin spelling into Amharic (never raises)."""
    try:
        return AmharicService().to_amharic_phonetic(text)
    except Exception:
        return text
