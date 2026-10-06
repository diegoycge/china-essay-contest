import re

CJK = r"㐀-䶿一-鿿豈-﫿"
_CJK_RE = re.compile(f"[{CJK}]")
_WORD_RE = re.compile(r"[A-Za-z0-9À-ɏ]+(?:['’\-][A-Za-z0-9À-ɏ]+)*")


def count_words(text):
    """Words in Latin-script text plus one per CJK character.

    Judges may write comments in English or Chinese; the JavaScript counter
    in sheet.js mirrors this rule so the live count matches the server.
    """
    if not text:
        return 0
    return len(_CJK_RE.findall(text)) + len(_WORD_RE.findall(_CJK_RE.sub(" ", text)))
