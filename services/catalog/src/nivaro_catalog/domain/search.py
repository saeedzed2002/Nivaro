import re
import unicodedata


def normalize_search(value: str) -> str:
    replacements: dict[str, str | int | None] = {"ي": "ی", "ك": "ک", "\u200c": " "}
    normalized = unicodedata.normalize("NFKC", value).translate(str.maketrans(replacements))
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def search_terms(value: str) -> list[str]:
    """Bounded literal prefix tokens; SQL metacharacters are not query syntax."""
    return list(dict.fromkeys(normalize_search(value).split()))[:12]
