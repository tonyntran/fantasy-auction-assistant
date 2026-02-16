"""
Fuzzy name matching utility.

Handles the many ways a player name can appear:
  - ESPN:    "A.J. Brown"          CSV: "AJ Brown"
  - ESPN:    "Patrick Mahomes"     CSV: "Patrick Mahomes II"
  - ESPN:    "Travis Etienne Jr."  CSV: "Travis Etienne"
  - ESPN:    "Kenneth Walker III"  CSV: "Kenneth Walker III"
  - DOM:     "D. Henry"            CSV: "Derrick Henry"

Strategy:
  1. Aggressive normalization (strip punctuation, suffixes, lowercase)
  2. Exact match on normalized form
  3. If no exact match, use RapidFuzz token_sort_ratio with a threshold
  4. Cache all resolved lookups so we only fuzzy-match once per name variant
"""

import re
from typing import Optional

from rapidfuzz import fuzz, process

# Suffixes that ESPN and CSV may include or omit inconsistently
_SUFFIXES = re.compile(
    r"\s+(jr\.?|sr\.?|ii|iii|iv|v|2nd|3rd)$", re.IGNORECASE
)

# Punctuation that varies between sources (A.J. vs AJ, D'Andre vs DAndre)
_PUNCTUATION = re.compile(r"[.\-'']")

# Minimum fuzzy score to accept a match (0-100)
FUZZY_THRESHOLD = 82


def normalize_name(name: str) -> str:
    """
    Aggressively normalize a player name for exact-match lookups.
    "A.J. Brown Jr." -> "aj brown"
    "Patrick Mahomes II" -> "patrick mahomes"
    "Travis Etienne Jr." -> "travis etienne"
    "D'Andre Swift" -> "dandre swift"
    """
    s = name.strip().lower()
    s = _PUNCTUATION.sub("", s)      # Remove dots, hyphens, apostrophes
    s = _SUFFIXES.sub("", s)         # Remove Jr, Sr, II, III, etc.
    s = re.sub(r"\s+", " ", s)       # Collapse multiple spaces
    return s.strip()


class NameResolver:
    """
    Maps incoming player names (from ESPN/extension) to canonical keys
    in the DraftState.players dict.

    Usage:
        resolver = NameResolver()
        resolver.build_index(state.players)  # call once after CSV load
        key = resolver.resolve("A.J. Brown")  # returns "aj brown" or similar
    """

    def __init__(self):
        # canonical_key -> normalized form (for fuzzy matching corpus)
        self._normalized_to_canonical: dict[str, str] = {}
        # lookup cache: raw incoming name -> canonical key (or None)
        self._cache: dict[str, Optional[str]] = {}
        # list of (normalized_name, canonical_key) for fuzzy search
        self._corpus: list[tuple[str, str]] = []

    def build_index(self, players: dict[str, object]):
        """
        Build the matching index from the state's player dict.
        `players` is keyed by the state's _normalize_name() output.
        """
        self._normalized_to_canonical.clear()
        self._cache.clear()
        self._corpus.clear()

        for canonical_key, ps in players.items():
            # The canonical key is already state._normalize_name(csv_name)
            # We also store an aggressively normalized version for matching
            display_name = ps.projection.player_name
            aggressive = normalize_name(display_name)

            self._normalized_to_canonical[aggressive] = canonical_key
            self._corpus.append((aggressive, canonical_key))

            # Also index the canonical key itself (may differ slightly)
            if canonical_key != aggressive:
                self._normalized_to_canonical[canonical_key] = canonical_key

    def resolve(self, incoming_name: str) -> Optional[str]:
        """
        Resolve an incoming player name to a canonical state.players key.
        Returns None if no match found above the threshold.
        """
        if not incoming_name:
            return None

        # Check cache first
        if incoming_name in self._cache:
            return self._cache[incoming_name]

        # Step 1: Try aggressive normalization for exact match
        aggressive = normalize_name(incoming_name)

        if aggressive in self._normalized_to_canonical:
            canonical = self._normalized_to_canonical[aggressive]
            self._cache[incoming_name] = canonical
            return canonical

        # Step 2: Fuzzy match against the corpus
        if not self._corpus:
            self._cache[incoming_name] = None
            return None

        corpus_names = [name for name, _ in self._corpus]
        result = process.extractOne(
            aggressive,
            corpus_names,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=FUZZY_THRESHOLD,
        )

        if result is not None:
            matched_name, score, idx = result
            canonical = self._corpus[idx][1]
            self._cache[incoming_name] = canonical
            return canonical

        # No match found
        self._cache[incoming_name] = None
        return None

    def resolve_or_original(self, incoming_name: str, fallback_normalize) -> str:
        """
        Resolve to canonical key, or fall back to the original normalization.
        `fallback_normalize` is the state's _normalize_name function.
        """
        resolved = self.resolve(incoming_name)
        if resolved is not None:
            return resolved
        return fallback_normalize(incoming_name)
