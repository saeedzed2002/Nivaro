import re
import unicodedata


def normalize_search(value: str) -> str:
    replacements: dict[str, str | int | None] = {"ي": "ی", "ك": "ک", "\u200c": " "}
    normalized = unicodedata.normalize("NFKC", value).translate(str.maketrans(replacements))
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def search_terms(value: str) -> list[str]:
    """Bounded literal prefix tokens; SQL metacharacters are not query syntax."""
    return list(dict.fromkeys(normalize_search(value).split()))[:12]


def search_index(value: str) -> list[str]:
    """Literal token prefixes for the catalog GIN index, shared by seed and staff writes."""
    words = normalize_search(value).split()
    return sorted({word[:length] for word in words for length in range(1, min(len(word), 100) + 1)})
