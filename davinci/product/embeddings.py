"""Explicit, independent, zero-network embedding adapter. No generation-provider imports."""

import hashlib
import math
import re

from davinci.models import digest


def tokens(text):
    return re.findall(r"[a-z0-9_]+", text.lower())[:2000]


class Embeddings:
    def __init__(self, settings):
        self.settings = settings
        self.identity = digest(settings.model_dump())

    def encode(self, text):
        if self.settings.adapter == "disabled":
            return None
        # Hashed lexical features, not a downloaded semantic model or a paid API.
        result = [0.0] * self.settings.dimensions
        for token in tokens(text):
            raw = hashlib.sha256(token.encode()).digest()
            result[int.from_bytes(raw[:8], "big") % len(result)] += 1 if raw[8] & 1 else -1
        norm = math.sqrt(sum(x * x for x in result))
        return [v / norm for v in result] if norm else result

    def similarity(self, query, vector):
        if len(vector) != self.settings.dimensions or any(not math.isfinite(v) for v in vector):
            raise ValueError("Invalid embedding dimensions or values")
        return sum(a * b for a, b in zip(query, vector))
