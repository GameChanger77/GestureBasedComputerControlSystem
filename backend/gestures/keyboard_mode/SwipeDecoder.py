from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


class SwipeDecoder:
    """
    Lightweight swipe trace decoder tuned for low CPU cost.

    Input traces are expected to be lowercase letter sequences with consecutive
    duplicates already collapsed.
    """
    _KEYBOARD_POSITIONS: Dict[str, Tuple[float, float]] = {
        **{ch: (float(i), 0.0) for i, ch in enumerate("qwertyuiop")},
        **{ch: (float(i) + 0.5, 1.0) for i, ch in enumerate("asdfghjkl")},
        **{ch: (float(i) + 1.0, 2.0) for i, ch in enumerate("zxcvbnm")},
    }
    _COLLINEAR_EPS = 0.35

    def __init__(self, lexicon_path: Path, max_words: Optional[int] = None):
        self.lexicon_path = Path(lexicon_path)
        self.max_words = None if max_words is None else max(1, int(max_words))
        self._rank_prior_weight = 0.35

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

    @classmethod
    def _simplify_trace_geometry(cls, trace: str) -> str:
        """
        Reduce long straight runs across adjacent keys into endpoints so
        over-sampled swipes preserve intent (e.g., w->...->o->...->r->d).
        """
        if len(trace) < 3:
            return trace

        simplified: List[str] = []
        for ch in trace:
            if simplified and ch == simplified[-1]:
                continue
            simplified.append(ch)

            changed = True
            while len(simplified) >= 3 and changed:
                changed = False
                a, b, c = simplified[-3], simplified[-2], simplified[-1]
                pa = cls._KEYBOARD_POSITIONS.get(a)
                pb = cls._KEYBOARD_POSITIONS.get(b)
                pc = cls._KEYBOARD_POSITIONS.get(c)
                if pa is None or pb is None or pc is None:
                    break

                v1x = pb[0] - pa[0]
                v1y = pb[1] - pa[1]
                v2x = pc[0] - pb[0]
                v2y = pc[1] - pb[1]
                cross = abs((v1x * v2y) - (v1y * v2x))
                dot = (v1x * v2x) + (v1y * v2y)

                # Remove middle points while movement direction is consistent.
                if cross <= cls._COLLINEAR_EPS and dot > 0.0:
                    simplified.pop(-2)
                    changed = True

        simplified_trace = "".join(simplified)
        return simplified_trace if len(simplified_trace) >= 2 else trace

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
        if trace_len <= 0 or cand_len <= 0:
            return 0.0
        # Similar lengths are generally better; avoid biasing toward very short
        # words on noisy traces.
        delta = abs(trace_len - cand_len)
        denom = float(max(trace_len, cand_len))
        return max(0.0, 1.0 - (float(delta) / denom))

    @staticmethod
    def _is_probably_alphabetical(words: List[str]) -> bool:
        # If the list is alphabetically sorted, file-order rank is not a good
        # frequency prior (it over-biases early letters like 'a').
        if len(words) < 128:
            return False
        sample = words[: min(5000, len(words))]
        non_decreasing = 0
        for idx in range(1, len(sample)):
            if sample[idx - 1] <= sample[idx]:
                non_decreasing += 1
        ratio = float(non_decreasing) / float(max(1, len(sample) - 1))
        return ratio >= 0.985

    @staticmethod
    def _downsample_evenly(words: List[str], target_count: int) -> List[str]:
        if target_count <= 0 or len(words) <= target_count:
            return list(words)
        if target_count == 1:
            return [words[0]]
        step = float(len(words) - 1) / float(target_count - 1)
        selected: List[str] = []
        seen = set()
        for i in range(target_count):
            idx = int(round(i * step))
            idx = max(0, min(len(words) - 1, idx))
            word = words[idx]
            if word in seen:
                continue
            seen.add(word)
            selected.append(word)
        # Pad deterministically if rounding collisions reduced count.
        if len(selected) < target_count:
            for word in words:
                if word in seen:
                    continue
                selected.append(word)
                seen.add(word)
                if len(selected) >= target_count:
                    break
        return selected[:target_count]

    @staticmethod
    def _stratified_alpha_subset(words: List[str], target_count: int) -> List[str]:
        if target_count <= 0 or len(words) <= target_count:
            return list(words)

        buckets: Dict[str, List[int]] = {chr(code): [] for code in range(ord("a"), ord("z") + 1)}
        for idx, word in enumerate(words):
            head = word[0]
            if head in buckets:
                buckets[head].append(idx)

        # First pass: give each letter an equal base budget.
        base_quota = max(1, target_count // len(buckets))
        quota_by_letter: Dict[str, int] = {}
        selected_total = 0
        for letter, idxs in buckets.items():
            quota = min(len(idxs), base_quota)
            quota_by_letter[letter] = quota
            selected_total += quota

        # Second pass: distribute remaining budget proportionally to leftover size.
        remaining_budget = max(0, target_count - selected_total)
        if remaining_budget > 0:
            leftovers = {
                letter: max(0, len(buckets[letter]) - quota_by_letter[letter])
                for letter in buckets
            }
            while remaining_budget > 0:
                # Pick letter with largest leftover pool; deterministic tie-break by letter.
                letter = max(leftovers.keys(), key=lambda k: (leftovers[k], -ord(k)))
                if leftovers[letter] <= 0:
                    break
                quota_by_letter[letter] += 1
                leftovers[letter] -= 1
                remaining_budget -= 1

        selected_indices: List[int] = []
        for letter in sorted(buckets.keys()):
            idxs = buckets[letter]
            quota = min(len(idxs), quota_by_letter.get(letter, 0))
            if quota <= 0:
                continue
            if quota >= len(idxs):
                selected_indices.extend(idxs)
            else:
                picked_local = set()

                # Keep short words (more likely common/useful for swipe typing).
                short_quota = max(1, int(round(quota * 0.55)))
                for idx in sorted(idxs, key=lambda i: (len(words[i]), i)):
                    picked_local.add(idx)
                    if len(picked_local) >= short_quota:
                        break

                # Keep some bucket-wide coverage to avoid overfitting to short words.
                remaining = quota - len(picked_local)
                if remaining > 0:
                    candidates = [idx for idx in idxs if idx not in picked_local]
                    if candidates:
                        if remaining >= len(candidates):
                            picked_local.update(candidates)
                        elif remaining == 1:
                            picked_local.add(candidates[len(candidates) // 2])
                        else:
                            step = float(len(candidates) - 1) / float(remaining - 1)
                            for i in range(remaining):
                                pick = candidates[int(round(i * step))]
                                picked_local.add(pick)

                selected_indices.extend(sorted(picked_local))

        selected_indices = sorted(set(selected_indices))
        if len(selected_indices) > target_count:
            selected_indices = selected_indices[:target_count]
        elif len(selected_indices) < target_count:
            # Fill any shortfall uniformly from the global list.
            selected_set = set(selected_indices)
            fillers = []
            step = float(len(words) - 1) / float(max(1, target_count - len(selected_indices)))
            probe_count = max(1, target_count - len(selected_indices))
            for i in range(probe_count * 2):
                idx = int(round(i * step))
                idx = max(0, min(len(words) - 1, idx))
                if idx in selected_set:
                    continue
                selected_set.add(idx)
                fillers.append(idx)
                if len(selected_indices) + len(fillers) >= target_count:
                    break
            selected_indices.extend(sorted(fillers))
            selected_indices = selected_indices[:target_count]

        return [words[idx] for idx in selected_indices]

    def _load_lexicon(self) -> None:
        if not self.lexicon_path.exists():
            return

        seen = set()
        all_words: List[str] = []
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
                all_words.append(word)

        if not all_words:
            return

        alphabetical = self._is_probably_alphabetical(all_words)
        if self.max_words is not None and len(all_words) > self.max_words:
            if alphabetical:
                # Preserve full-alphabet coverage for large alphabetical lists.
                self.words = self._stratified_alpha_subset(all_words, self.max_words)
                self._rank_prior_weight = 0.02
            else:
                # Keep head-biased order for frequency-ranked lists.
                self.words = all_words[: self.max_words]
                self._rank_prior_weight = 0.35
        else:
            self.words = all_words
            self._rank_prior_weight = 0.35 if not alphabetical else 0.02

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
        raw_trace = "".join(ch for ch in trace_letters if isinstance(ch, str) and len(ch) == 1 and ch.isalpha()).lower()
        raw_trace = self._collapse_repeats(raw_trace)
        if len(raw_trace) < 2 or not self.words:
            return "", 0.0, []
        simplified_trace = self._simplify_trace_geometry(raw_trace)

        # Union candidate pools from both raw and simplified traces so
        # directional simplification can recover intended edges while still
        # preserving raw-path fallbacks.
        candidate_pool = set()
        for trace in (raw_trace, simplified_trace):
            edge = (trace[0], trace[-1])
            candidate_pool.update(self._candidates_by_edge.get(edge, []))
            candidate_pool.update(self._candidates_by_start.get(trace[0], []))

        if not candidate_pool:
            # Always provide a best guess for swipe typing UX; decode happens on
            # commit only, so a full-lexicon fallback remains cheap enough.
            candidate_indices = list(range(len(self.words)))
        else:
            candidate_indices = list(candidate_pool)

        # Keep length filtering permissive to tolerate noisy swipes.
        min_len = 2
        max_len = min(16, max(len(raw_trace) + 4, int(len(raw_trace) * 1.35) + 2))
        raw_bigrams = self._bigrams(raw_trace)
        raw_letters_set = set(raw_trace)
        simplified_bigrams = self._bigrams(simplified_trace)
        simplified_letters_set = set(simplified_trace)

        pre_scored: List[Tuple[float, int]] = []
        for idx in set(candidate_indices):
            word = self.words[idx]
            if len(word) < min_len or len(word) > max_len:
                continue

            skeleton = self.word_skeletons[idx]
            if not skeleton:
                continue

            def _quick_for(trace: str, trace_bigrams: set[str], trace_letters: set[str]) -> float:
                edge_match = 0.0
                edge_match += 0.5 if skeleton[0] == trace[0] else 0.0
                edge_match += 0.5 if skeleton[-1] == trace[-1] else 0.0
                bigram_overlap = self._overlap_ratio(self.word_bigrams[idx], trace_bigrams)
                letter_overlap = self._overlap_ratio(self.word_letters[idx], trace_letters)
                length_delta = abs(len(skeleton) - len(trace)) / float(max(len(skeleton), len(trace), 1))
                return (
                    (0.35 * edge_match)
                    + (0.35 * bigram_overlap)
                    + (0.20 * letter_overlap)
                    - (0.20 * length_delta)
                )

            quick_raw = _quick_for(raw_trace, raw_bigrams, raw_letters_set)
            quick_simplified = _quick_for(simplified_trace, simplified_bigrams, simplified_letters_set)

            missing_in_raw = len(self.word_letters[idx] - raw_letters_set)
            quick_score = (0.65 * quick_simplified) + (0.35 * quick_raw) - (0.06 * missing_in_raw)
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

            def _feature_for(trace: str, trace_bigrams: set[str]) -> Tuple[float, float, float, float]:
                edge_match = 0.0
                edge_match += 0.5 if skeleton[0] == trace[0] else 0.0
                edge_match += 0.5 if skeleton[-1] == trace[-1] else 0.0
                bigram_overlap = self._overlap_ratio(self.word_bigrams[idx], trace_bigrams)
                shape_score = (0.50 * edge_match) + (0.50 * bigram_overlap)

                dist = self._weighted_edit_distance(trace, skeleton)
                max_ref = float(max(len(trace), len(skeleton), 1))
                edit_score = max(0.0, 1.0 - (dist / max_ref))
                coverage_score = self._ordered_match_ratio(skeleton, trace)
                length_score = self._length_bonus(len(trace), len(skeleton))
                return (shape_score, edit_score, coverage_score, length_score)

            shape_s, edit_s, coverage_s, length_s = _feature_for(simplified_trace, simplified_bigrams)
            shape_r, edit_r, coverage_r, length_r = _feature_for(raw_trace, raw_bigrams)
            prior_score = self._rank_prior(idx, len(self.words))
            raw_letter_overlap = self._overlap_ratio(self.word_letters[idx], raw_letters_set)
            missing_in_raw = len(self.word_letters[idx] - raw_letters_set)

            prior_w = self._rank_prior_weight
            data_score = (
                (0.28 * shape_s)
                + (0.28 * edit_s)
                + (0.10 * coverage_s)
                + (0.11 * length_s)
                + (0.10 * shape_r)
                + (0.05 * edit_r)
                + (0.03 * coverage_r)
                + (0.05 * raw_letter_overlap)
                - (0.04 * missing_in_raw)
            )
            total = ((1.0 - prior_w) * data_score) + (prior_w * prior_score)
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
