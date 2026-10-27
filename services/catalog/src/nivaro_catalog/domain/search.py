import re
import unicodedata


def normalize_search(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).translate(
        str.maketrans({"ي": "ی", "ك": "ک", "\u200c": " "})
    )
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def search_terms(value: str) -> list[str]:
    """Bounded literal prefix tokens; SQL metacharacters are not query syntax."""
    return list(dict.fromkeys(normalize_search(value).split()))[:12]
