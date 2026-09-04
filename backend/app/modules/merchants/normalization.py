"""Matching keys only; never rewrite imported raw fields."""

import hashlib
import unicodedata


def comparison_key(value: str) -> str:
    # NFC retains meaningful Unicode. Turkic casing keeps i/İ and ı/I as distinct pairs.
    value = unicodedata.normalize("NFC", value).replace("İ", "i").replace("I", "ı")
    return " ".join(unicodedata.normalize("NFC", value.casefold()).split())


def merchant_context(description_raw: str, merchant_raw: str | None) -> str:
    return comparison_key(merchant_raw or "") or comparison_key(description_raw)


def merchant_rule_key(description_raw: str, merchant_raw: str | None) -> str:
    # Exact normalized context identity, bounded for the existing VARCHAR(255).
    # A versioned digest avoids truncation collisions and copying long raw descriptions.
    context = merchant_context(description_raw, merchant_raw)
    return "v1:" + hashlib.sha256(context.encode("utf-8")).hexdigest()
