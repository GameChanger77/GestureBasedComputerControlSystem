from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


class SwipeDecoder:
    """
    Lightweight swipe trace decoder tuned for low CPU cost.

    Input traces are expected to be lowercase letter sequences with consecutive
    duplicates already collapsed.
    """

    def __init__(self, lexicon_path: Path, max_words: int = 12000):
        self.lexicon_path = Path(lexicon_path)
        self.max_words = max(1, int(max_words))

        self.words: List[str] = []
        self.word_skeletons: List[str] = []
        self.word_bigrams: List[set[str]] = []
        self.word_letters: List[set[str]] = []
        self._rank_by_word: Dict[str, int] = {}
        self._candidates_by_edge: Dict[Tuple[str, str], List[int]] = {}
        self._candidates_by_start: Dict[str, List[int]] = {}

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

    @staticmethod
    def _bigrams(text: str) -> set[str]:
        if len(text) < 2:
            return set()
        return {text[i:i + 2] for i in range(len(text) - 1)}

    @staticmethod
    def _overlap_ratio(a: set[str], b: set[str]) -> float:
        if not a:
            return 0.0
        return float(len(a & b)) / float(len(a))

    @staticmethod
    def _ordered_match_ratio(candidate: str, trace: str) -> float:
        if not candidate:
            return 0.0
        i = 0
        for ch in trace:
            if i < len(candidate) and ch == candidate[i]:
                i += 1
                if i == len(candidate):
                    break
        return float(i) / float(len(candidate))

    @staticmethod
    def _rank_prior(rank_idx: int, total_words: int) -> float:
        if total_words <= 1:
            return 1.0
        normalized = float(rank_idx) / float(max(1, total_words - 1))
        return max(0.0, 1.0 - math.sqrt(normalized))

    @staticmethod
    def _length_bonus(trace_len: int, cand_len: int) -> float:
        if trace_len <= 0:
            return 0.0
        raw = float(trace_len - cand_len) / float(trace_len)
        return max(-1.0, min(1.0, raw))

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
            self.word_bigrams.append(self._bigrams(skeleton))
            self.word_letters.append(set(skeleton))
            edge = (word[0], word[-1])
            self._candidates_by_edge.setdefault(edge, []).append(rank)
            self._candidates_by_start.setdefault(word[0], []).append(rank)

    def decode(self, trace_letters: Sequence[str], top_k: int = 3) -> Tuple[str, float, List[str]]:
        top_k = max(1, int(top_k))
        trace = "".join(ch for ch in trace_letters if isinstance(ch, str) and len(ch) == 1 and ch.isalpha()).lower()
        trace = self._collapse_repeats(trace)
        if len(trace) < 2 or not self.words:
            return "", 0.0, []

        edge = (trace[0], trace[-1])
        candidate_indices = list(self._candidates_by_edge.get(edge, []))
        if not candidate_indices:
            candidate_indices = list(self._candidates_by_start.get(trace[0], []))

        if not candidate_indices:
            return "", 0.0, []

        # Keep length filtering permissive to tolerate noisy swipes.
        min_len = 2
        max_len = min(16, max(len(trace) + 4, int(len(trace) * 1.35) + 2))
        trace_bigrams = self._bigrams(trace)
        trace_letters_set = set(trace)

        pre_scored: List[Tuple[float, int]] = []
        for idx in set(candidate_indices):
            word = self.words[idx]
            if len(word) < min_len or len(word) > max_len:
                continue

            skeleton = self.word_skeletons[idx]
            edge_match = 0.0
            if skeleton and trace:
                edge_match += 0.5 if skeleton[0] == trace[0] else 0.0
                edge_match += 0.5 if skeleton[-1] == trace[-1] else 0.0
            bigram_overlap = self._overlap_ratio(self.word_bigrams[idx], trace_bigrams)
            letter_overlap = self._overlap_ratio(self.word_letters[idx], trace_letters_set)
            length_delta = abs(len(skeleton) - len(trace)) / float(max(len(skeleton), len(trace), 1))
            quick_score = (
                (0.35 * edge_match)
                + (0.35 * bigram_overlap)
                + (0.20 * letter_overlap)
                - (0.20 * length_delta)
            )
            pre_scored.append((quick_score, idx))

        if not pre_scored:
            return "", 0.0, []

        pre_scored.sort(key=lambda item: (-item[0], item[1]))
        shortlist = [idx for _, idx in pre_scored[: min(400, len(pre_scored))]]

        scored: List[Tuple[float, int, str]] = []
        for idx in shortlist:
            word = self.words[idx]
            skeleton = self.word_skeletons[idx]
            if not skeleton:
                continue

            edge_match = 0.0
            if skeleton and trace:
                edge_match += 0.5 if skeleton[0] == trace[0] else 0.0
                edge_match += 0.5 if skeleton[-1] == trace[-1] else 0.0
            bigram_overlap = self._overlap_ratio(self.word_bigrams[idx], trace_bigrams)
            shape_score = (0.50 * edge_match) + (0.50 * bigram_overlap)

            dist = self._weighted_edit_distance(trace, skeleton)
            max_ref = float(max(len(trace), len(skeleton), 1))
            edit_score = max(0.0, 1.0 - (dist / max_ref))

            coverage_score = self._ordered_match_ratio(skeleton, trace)
            length_score = self._length_bonus(len(trace), len(skeleton))
            prior_score = self._rank_prior(idx, len(self.words))

            total = (
                (0.20 * shape_score)
                + (0.20 * edit_score)
                + (0.10 * coverage_score)
                + (0.15 * length_score)
                + (0.35 * prior_score)
            )
            scored.append((total, idx, word))

        if not scored:
            return "", 0.0, []

        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        top = scored[:top_k]
        best_score, _, best_word = top[0]
        second_score = top[1][0] if len(top) > 1 else (best_score - 0.20)

        margin = best_score - second_score
        confidence = max(0.0, min(1.0, (best_score * 0.60) + (margin * 0.80)))
        candidates = [item[2] for item in top]
        return best_word, confidence, candidates
