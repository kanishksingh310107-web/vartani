"""Script handling: detect script, Romanize native text, and "bridge" Roman text back to native script.

Design notes
- `romanize` is deliberately identical to the paper's C1 condition (ITRANS, lower-cased) so that results
  can be compared with the Colab study.
- `bridge` is the mitigation under test: Roman -> native script. It is a *rule-based approximation*
  (ITRANS + final-schwa fix + a small Hindi function-word list). The report measures whether it helps your
  model on your data instead of assuming it does.
"""
from __future__ import annotations
import re
from indic_transliteration import sanscript

LANG_INFO = {
    "hi": {"name": "Hindi", "native": "हिन्दी", "script": sanscript.DEVANAGARI, "virama": "\u094d"},
    "bn": {"name": "Bengali", "native": "বাংলা", "script": sanscript.BENGALI, "virama": "\u09cd"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "script": sanscript.TAMIL, "virama": "\u0bcd"},
}
WORD_RE = re.compile(r"[A-Za-z]+")


def native_ratio(text: str) -> float:
    """Share of letters that are in an Indic block (0 = all Latin, 1 = all native)."""
    native = latin = 0
    for ch in text:
        o = ord(ch)
        if 0x0900 <= o <= 0x0DFF:
            native += 1
        elif ch.isascii() and ch.isalpha():
            latin += 1
    return native / (native + latin) if native + latin else 0.0


def script_of(text: str) -> str:
    r = native_ratio(text)
    return "native" if r > 0.7 else "roman" if r < 0.3 else "mixed"


def romanize(text: str, lang: str) -> str:
    """Paper-compatible Romanization (condition C1): ITRANS, lower-cased, '~' and '.' removed."""
    out = sanscript.transliterate(text, LANG_INFO[lang]["script"], sanscript.ITRANS)
    return out.lower().replace("~", "").replace(".", "")


# ---- Roman -> native "bridge" -------------------------------------------------------------------------------
_HI_WORDS = dict(
    hai="है", hain="हैं", ho="हो", hoti="होती", hota="होता", hote="होते", hui="हुई", hua="हुआ", hue="हुए",
    tha="था", thi="थी", the="थे", thin="थीं", kya="क्या", kyon="क्यों", kyun="क्यूँ", kaise="कैसे", kaisi="कैसी",
    kaisa="कैसा", kaun="कौन", kahan="कहाँ", kab="कब", kitna="कितना", kitni="कितनी", kitne="कितने", kis="किस",
    kisne="किसने", ki="की", ke="के", ka="का", ko="को", se="से", mein="में", me="में", par="पर", pe="पे", tak="तक",
    aur="और", ya="या", lekin="लेकिन", magar="मगर", bahut="बहुत", bhi="भी", hi="ही", to="तो", toh="तो",
    nahi="नहीं", nahin="नहीं", na="न", mat="मत", agar="अगर", jab="जब", tab="तब", jo="जो", woh="वह", wo="वो",
    yeh="यह", ye="ये", us="उस", ek="एक", do="दो", teen="तीन", char="चार", paanch="पाँच", chhah="छह",
    chhe="छह", saat="सात", aath="आठ", nau="नौ", das="दस", gyarah="ग्यारह", main="मैं", mai="मैं", hum="हम",
    tum="तुम", aap="आप", mera="मेरा", meri="मेरी", mere="मेरे", hamara="हमारा", unka="उनका", uska="उसका",
    uski="उसकी", uske="उसके", iska="इसका", iski="इसकी", iske="इसके", sab="सब", sabhi="सभी", kuch="कुछ",
    koi="कोई", saath="साथ", liye="लिए", wala="वाला", wali="वाली", wale="वाले", karna="करना", karne="करने",
    karta="करता", karti="करती", karte="करते", kiya="किया", gaya="गया", gayi="गई", gaye="गए", jaata="जाता",
    jaati="जाती", jaate="जाते", jaana="जाना", aata="आता", aati="आती", aate="आते", raha="रहा", rahi="रही",
    rahe="रहे", sakta="सकता", sakti="सकती", sakte="सकते", chahiye="चाहिए", dopahar="दोपहर", subah="सुबह",
    shaam="शाम", raat="रात", din="दिन", roz="रोज़", suraj="सूरज", dhoop="धूप", paani="पानी", baarish="बारिश",
    ghar="घर", phir="फिर", baad="बाद", samay="समय", baje="बजे", ghanta="घंटा", minute="मिनट", use="उसे",
    isliye="इसलिए", kyonki="क्योंकि", sirf="सिर्फ़", keval="केवल", bilkul="बिल्कुल", zyada="ज़्यादा",
    tez="तेज़", thandi="ठंडी", halki="हल्की", poorab="पूरब", paschim="पश्चिम", ugta="उगता", doobta="डूबता",
    kiranen="किरणें", beti="बेटी", kisaan="किसान", fasal="फ़सल", dhaan="धान", vigyaan="विज्ञान",
    ganit="गणित", kathin="कठिन", pasand="पसंद", padhti="पढ़ती", padhta="पढ़ता",
)
_HI_WORDS["is"] = "इस"          # `is` is a Python keyword, so it cannot be a dict() kwarg
_PRE = [("ee", "ii"), ("w", "v"), ("z", "j"), ("q", "k"), ("f", "ph"), ("x", "ks")]
_cache: dict = {}


def _bridge_word(word: str, lang: str) -> str:
    w = word.lower()
    if lang == "hi" and w in _HI_WORDS:
        return _HI_WORDS[w]
    key = (lang, w)
    if key in _cache:
        return _cache[key]
    s = w
    for a, b in _PRE:
        s = s.replace(a, b)
    s = re.sub(r"c(?!h)", "k", s)
    out = sanscript.transliterate(s, sanscript.ITRANS, LANG_INFO[lang]["script"])
    vir = LANG_INFO[lang]["virama"]
    if lang in ("hi", "bn") and out.endswith(vir):      # final consonant keeps its inherent vowel
        out = out[:-1]
    if lang == "ta" and "ae" not in w:                  # Roman Tamil writes short e/o as plain e/o
        out = out.replace("ே", "ெ").replace("ஏ", "எ").replace("ோ", "ொ").replace("ஓ", "ஒ")
    _cache[key] = out
    return out


def bridge(text: str, lang: str) -> str:
    """Convert Roman words in `text` to native script (approximate). Digits/punctuation are untouched."""
    return WORD_RE.sub(lambda m: _bridge_word(m.group(0), lang), text)
