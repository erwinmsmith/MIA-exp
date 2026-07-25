"""Adapters for the official Solo Performance Prompting benchmark datasets."""

from __future__ import annotations

import json
import re
from typing import Any

from .contracts import ItemScore
from .registry import BenchmarkSpec, get_benchmark


SPP_BENCHMARK_IDS = (
    "spp.logic-grid-puzzle",
    "spp.trivia-creative-writing-n5",
    "spp.trivia-creative-writing-n10",
    "spp.codenames-collaborative",
)

_FINAL_ANSWER = re.compile(
    r"(?:FINAL_ANSWER|FINAL ANSWER|Final answer|Answer)\s*:\s*"
    r"(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|10|[1-9])\b",
    re.IGNORECASE,
)
_ORDINALS = {
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
    "sixth": "6",
    "seventh": "7",
    "eighth": "8",
    "ninth": "9",
    "tenth": "10",
}


def load_instances(benchmark: str | BenchmarkSpec) -> list[dict[str, Any]]:
    spec = get_benchmark(benchmark) if isinstance(benchmark, str) else benchmark
    if spec.suite != "spp":
        raise ValueError(f"{spec.id} is not an SPP benchmark")
    with spec.data_path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _format_word_list(words: list[str]) -> str:
    return ", ".join(words)


def render_prompt(
    benchmark_id: str,
    instance: dict[str, Any],
    *,
    stage: str | None = None,
    hint: str | None = None,
) -> str:
    """Render a Roy-facing prompt without embedding benchmark answers."""

    if benchmark_id == "spp.logic-grid-puzzle":
        question = instance["inputs"].removesuffix("\nA:")
        return (
            "Solve this logic-grid puzzle. Check the clues and candidate house "
            "numbers carefully. Use Roy's normal delegation judgment: derive a "
            "team or subagent only if a distinct reasoning or verification role "
            "would improve reliability.\n\n"
            f"{question}\n\n"
            "End with exactly one machine-readable line: FINAL_ANSWER: <house number>"
        )

    if benchmark_id.startswith("spp.trivia-creative-writing-"):
        questions = "\n".join(
            f"{index}. {question}"
            for index, question in enumerate(instance["questions"], start=1)
        )
        return (
            f"Write one coherent story about {instance['topic']!r}. The story must "
            "naturally incorporate the answer to every trivia question below. "
            "Do not list the questions or explain your process in the final story. "
            "Resolve every question to its precise canonical answer before writing; "
            "when a person or work is commonly known by an alias, stage name, or "
            "alternate title, naturally include both names to remove ambiguity. "
            "Treat historical first/last claims as scope-sensitive: if reliable "
            "sources distinguish invention or an early/limited commercial release "
            "from mass-market sale, or nationwide ratification from a later "
            "state-law repeal, naturally preserve each supported milestone instead "
            "of silently collapsing them into one interpretation. "
            "Do not substitute a merely related person, place, work, or decade. "
            "Use the available read-only web.search and web.fetch tools to verify "
            "every answer against public evidence before writing. If you delegate "
            "factual research, give that researcher the web tools and require "
            "source-grounded answers that retain every materially different source "
            "scope and milestone. Citations do not need to appear in the story. "
            "Use Roy's normal delegation judgment; independent knowledge specialists "
            "and a final factuality/coherence reviewer may be useful when appropriate.\n\n"
            f"{questions}\n\n"
            "End with the complete story after a line containing FINAL_STORY:"
        )

    if benchmark_id == "spp.codenames-collaborative":
        word_list = _format_word_list(instance["word_list"])
        count = len(instance["target_words"])
        if stage == "spymaster":
            targets = _format_word_list(instance["target_words"])
            return (
                "You are the Spymaster in a Codenames collaboration. Produce one "
                f"single-word hint linking all {count} target words while avoiding "
                "associations with the distractors. Use Roy's normal delegation "
                "judgment and verify the hint against the entire board.\n\n"
                f"Target words: {targets}\n"
                f"Complete board: {word_list}\n\n"
                "Do not reveal the target words in the final line. End with exactly: "
                "FINAL_HINT: <one word>"
            )
        if stage == "guesser":
            if not hint:
                raise ValueError("the Codenames guesser stage requires a hint")
            return (
                "You are the Guesser in a fresh Codenames session. You cannot see "
                "the Spymaster's target words. Based only on the hint and board, "
                f"identify exactly {count} words. Use Roy's normal delegation judgment "
                "and have an independent critic check distractor risk when useful.\n\n"
                f"Hint: {hint}\n"
                f"Complete board: {word_list}\n\n"
                "End with one comma-separated line: "
                "FINAL_GUESSES: <word 1>, <word 2>, ..."
            )
        raise ValueError("Codenames requires stage='spymaster' or stage='guesser'")

    raise KeyError(f"unsupported SPP benchmark: {benchmark_id}")


def parse_logic_answer(response: str) -> str | None:
    matches = list(_FINAL_ANSWER.finditer(response))
    if not matches:
        return None
    raw = matches[-1].group(1).casefold()
    return _ORDINALS.get(raw, raw)


def parse_hint(response: str) -> str | None:
    matches = re.findall(
        r"(?:FINAL_HINT|FINAL HINT|Final hint)\s*:\s*([A-Za-z][A-Za-z'-]*)",
        response,
        flags=re.IGNORECASE,
    )
    if not matches:
        return None
    return matches[-1].strip().casefold()


def parse_guesses(response: str, board: list[str]) -> list[str] | None:
    matches = re.findall(
        r"(?:FINAL_GUESSES|FINAL GUESSES|Final guesses|Final answer|Answer)\s*:\s*([^\n]+)",
        response,
        flags=re.IGNORECASE,
    )
    if not matches:
        return None
    board_lookup = {word.casefold(): word.casefold() for word in board}
    guesses: list[str] = []
    for fragment in matches[-1].split(","):
        normalized = fragment.strip().strip(" .;:!?\"'").casefold()
        if normalized in board_lookup and normalized not in guesses:
            guesses.append(normalized)
    return guesses


def extract_story(response: str) -> str:
    marker = re.search(r"FINAL_STORY\s*:\s*", response, flags=re.IGNORECASE)
    return response[marker.end() :].strip() if marker else response.strip()


def score_response(
    benchmark_id: str,
    instance: dict[str, Any],
    response: str,
) -> ItemScore:
    """Apply the official task semantics through the common score contract."""

    if benchmark_id == "spp.logic-grid-puzzle":
        prediction = parse_logic_answer(response)
        target = str(instance["targets"][0])
        return ItemScore(
            metric="answer_recall",
            earned=int(prediction == target),
            possible=1,
            parsed=prediction is not None,
            details={"prediction": prediction, "target": target},
        )

    if benchmark_id.startswith("spp.trivia-creative-writing-"):
        story = extract_story(response)
        folded_story = story.casefold()
        matches: list[dict[str, Any]] = []
        for index, aliases in enumerate(instance["answers"]):
            matched_alias = next(
                (alias for alias in aliases if alias.casefold() in folded_story),
                None,
            )
            matches.append(
                {
                    "questionId": instance["question_ids"][index],
                    "matched": matched_alias is not None,
                    "alias": matched_alias,
                }
            )
        return ItemScore(
            metric="answer_recall",
            earned=sum(match["matched"] for match in matches),
            possible=len(matches),
            parsed=bool(story),
            details={"matches": matches},
        )

    if benchmark_id == "spp.codenames-collaborative":
        guesses = parse_guesses(response, instance["word_list"])
        targets = {word.casefold() for word in instance["target_words"]}
        guessed = set(guesses or [])
        matched = sorted(targets & guessed)
        return ItemScore(
            metric="target_word_recall",
            earned=len(matched),
            possible=len(targets),
            parsed=guesses is not None,
            details={
                "guesses": guesses,
                "matchedWords": matched,
                "targetWords": sorted(targets),
                "distractorGuesses": sorted(guessed - targets),
            },
        )

    raise KeyError(f"unsupported SPP benchmark: {benchmark_id}")
