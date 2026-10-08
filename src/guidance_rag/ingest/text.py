"""Text clean-up shared by the HTML and PDF parsers."""

import re
import unicodedata

# Characters used in place of a plain space. DGI 2024 maps its space glyph to U+0001;
# the rest are no-break, en, em, thin, hair, narrow no-break and ideographic spaces.
_SPACE_LIKE = dict.fromkeys(map(ord, "\x01\u00a0\u2002\u2003\u2009\u200a\u202f\u3000"), " ")
# Soft hyphen, zero-width space/joiners and byte-order mark.
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u00ad\u200b\u200c\u200d\ufeff"), None)
_LIGATURES = {
    ord(c): unicodedata.normalize("NFKC", c) for c in "\ufb00\ufb01\ufb02\ufb03\ufb04\ufb05\ufb06"
}
# FSSAI documents write degrees as a superscript zero ("4⁰C"); NFKC would make that "40C".
_SYMBOLS = {ord("\u2070"): "\u00b0"}


def clean_text(text: str) -> str:
    """Normalise whitespace and odd characters; keep the wording unchanged."""
    text = text.translate(_SPACE_LIKE).translate(_ZERO_WIDTH)
    text = text.translate(_LIGATURES).translate(_SYMBOLS)
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def join_lines(lines: list[str]) -> str:
    """Join wrapped lines into one string, keeping hyphens at line ends ('Twenty-' + 'fourth')."""
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not out:
            out = line
        elif out.endswith("-") and not out.endswith(" -"):
            out += line
        else:
            out += " " + line
    return out
