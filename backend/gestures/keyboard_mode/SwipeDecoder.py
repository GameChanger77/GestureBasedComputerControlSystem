from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


class SwipeDecoder:
    """
    Lightweight swipe trace decoder tuned for low CPU cost.

    Input traces are expected to be lowercase letter sequences with consecutive
    duplicates already collapsed.
    """

    def __init__(self, lexicon_path: Path, max_words: int = 6000):
        self.lexicon_path = Path(lexicon_path)
        self.max_words = max(1, int(max_words))

        self.words: List[str] = []
        self.word_skeletons: List[str] = []
        self._rank_by_word: Dict[str, int] = {}
        self._candidates_by_edge: Dict[Tuple[str, str], List[int]] = {}

        self._load_lexicon()

    @staticmethod
    def _collapse_repeats(text: str) -> str:
        if not text:
            return ""
        out = [text[0]]
        for ch in text[1:]:
            if ch != out[-1]:
                out.append(ch)
        return "".join(out)

    @staticmethod
    def _is_subsequence(sub: str, full: str) -> bool:
        if not sub:
            return True
        i = 0
        for ch in full:
            if ch == sub[i]:
                i += 1
                if i == len(sub):
                    return True
        return False

    @staticmethod
    def _weighted_edit_distance(a: str, b: str) -> float:
        # Small strings only, so classic DP is fine and predictable.
        if a == b:
            return 0.0
        if not a:
            return float(len(b))
        if not b:
            return float(len(a))

        ins_cost = 0.9
        del_cost = 0.9
        sub_cost = 1.2

        prev = [j * ins_cost for j in range(len(b) + 1)]
        for i, ca in enumerate(a, start=1):
            curr = [i * del_cost]
            for j, cb in enumerate(b, start=1):
                cost_sub = 0.0 if ca == cb else sub_cost
                curr.append(
                    min(
                        prev[j] + del_cost,
                        curr[j - 1] + ins_cost,
                        prev[j - 1] + cost_sub,
                    )
                )
            prev = curr
        return prev[-1]

    def _load_lexicon(self) -> None:
        if not self.lexicon_path.exists():
            return

        seen = set()
        with self.lexicon_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                word = line.strip().lower()
                if not word:
                    continue
                if not word.isalpha():
                    continue
                if len(word) < 2 or len(word) > 16:
                    continue
                if word in seen:
                    continue

                seen.add(word)
                self.words.append(word)
                if len(self.words) >= self.max_words:
                    break

        for rank, word in enumerate(self.words):
            self._rank_by_word[word] = rank
            skeleton = self._collapse_repeats(word)
            self.word_skeletons.append(skeleton)
            edge = (word[0], word[-1])
            self._candidates_by_edge.setdefault(edge, []).append(rank)

    def decode(self, trace_letters: Sequence[str], top_k: int = 3) -> Tuple[str, float, List[str]]:
        top_k = max(1, int(top_k))
        trace = "".join(ch for ch in trace_letters if isinstance(ch, str) and len(ch) == 1 and ch.isalpha()).lower()
        trace = self._collapse_repeats(trace)
        if len(trace) < 2 or not self.words:
            return "", 0.0, []

        edge = (trace[0], trace[-1])
        candidate_indices = self._candidates_by_edge.get(edge, [])

        if not candidate_indices:
            # Relaxed fallback to same first letter.
            candidate_indices = [
                idx for idx, word in enumerate(self.words)
                if word[0] == trace[0]
            ]
        if not candidate_indices:
            return "", 0.0, []

        # Swipes can contain substantial lateral noise. Keep lower bound permissive
        # and cap upper bound to avoid runaway candidate sets.
        min_len = 2
        max_len = min(16, max(len(trace) + 4, int(len(trace) * 1.25) + 2))

        scored = []
        for idx in candidate_indices:
            word = self.words[idx]
            if len(word) < min_len or len(word) > max_len:
                continue

            skeleton = self.word_skeletons[idx]
            # Noisy swipes commonly include extra letters; require candidate path
            # to appear in-order within the observed trace (not the reverse).
            if not self._is_subsequence(skeleton, trace):
                continue

            dist = self._weighted_edit_distance(trace, skeleton)
            max_ref = float(max(len(trace), len(skeleton), 1))
            norm_dist = dist / max_ref
            rank_prior = 1.00 * (1.0 - (idx / max(1, len(self.words))))
            score = (1.0 - norm_dist) + rank_prior
            scored.append((score, idx, word))

        if not scored:
            # Second-pass fallback without subsequence gate.
            for idx in candidate_indices:
                word = self.words[idx]
                if len(word) < min_len or len(word) > max_len:
                    continue
                skeleton = self.word_skeletons[idx]
                dist = self._weighted_edit_distance(trace, skeleton)
                max_ref = float(max(len(trace), len(skeleton), 1))
                norm_dist = dist / max_ref
                rank_prior = 0.75 * (1.0 - (idx / max(1, len(self.words))))
                score = (1.0 - norm_dist) + rank_prior
                scored.append((score, idx, word))

        if not scored:
            return "", 0.0, []

        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        top = scored[:top_k]
        best_score, _, best_word = top[0]
        second_score = top[1][0] if len(top) > 1 else (best_score - 0.25)

        margin = best_score - second_score
        confidence = max(0.0, min(1.0, (best_score * 0.7) + (margin * 0.9)))
        candidates = [item[2] for item in top]
        return best_word, confidence, candidates
