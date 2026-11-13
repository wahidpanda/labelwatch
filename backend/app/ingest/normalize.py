import re
import unicodedata

# Salt and hydrate words dropped so "Zolpidem Tartrate" and "zolpidem" match.
_SALT_WORDS = frozenset(
    {
        "acetate",
        "anhydrous",
        "besylate",
        "bisulfate",
        "bromide",
        "calcium",
        "chloride",
        "citrate",
        "dihydrate",
        "fumarate",
        "hcl",
        "hemihydrate",
        "hydrobromide",
        "hydrochloride",
        "hyclate",
        "magnesium",
        "maleate",
        "mesylate",
        "monohydrate",
        "oxalate",
        "phosphate",
        "potassium",
        "sodium",
        "succinate",
        "sulfate",
        "tartrate",
        "tosylate",
    }
)
_WS = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^a-z0-9 ]+")


def normalize_text(value: str) -> str:
    """Unicode NFKC and collapsed whitespace. Keeps case for display."""
    return _WS.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def hash_form(value: str) -> str:
    """Lowercase copy of the normalised text, used for hashing and comparison."""
    return normalize_text(value).lower()


def normalize_ingredient(name: str) -> str:
    words = _NON_WORD.sub(" ", normalize_text(name).lower()).split()
    kept = [w for w in words if w not in _SALT_WORDS]
    return " ".join(kept or words)


def join_units(units: list[str] | tuple[str, ...]) -> str:
    return "\n".join(units)


def split_units(body: str) -> list[str]:
    return [line for line in body.split("\n") if line]
