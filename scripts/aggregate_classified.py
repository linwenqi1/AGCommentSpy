#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ALLOWED_DIMENSIONS = [
    "功能体验",
    "系统与机型适配",
    "稳定性与性能",
    "UI与交互",
    "运营与规则",
    "体验赞赏",
    "内容生态",
]

ALLOWED_SENTIMENTS = ["Negative", "Positive", "Neutral"]


def extract_json_text(raw_text: str) -> str:
    if not isinstance(raw_text, str):
        raise ValueError("raw_text must be a string")
    stripped = raw_text.strip()
    # try fenced code block
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    # try to find first/last brace
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return stripped[first_brace : last_brace + 1].strip()

    # fallback
    return stripped


def parse_raw_response(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None

    if isinstance(raw, dict):
        return raw

    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            try:
                json_text = extract_json_text(raw)
                return json.loads(json_text)
            except Exception:
                return None

    return None


def make_empty_result() -> dict[str, dict[str, list[dict[str, str]]]]:
    return {
        dim: {sent: [] for sent in ALLOWED_SENTIMENTS} for dim in ALLOWED_DIMENSIONS
    }


def aggregate(input_path: Path, output_path: Path) -> None:
    rows = json.loads(input_path.read_text(encoding="utf-8"))
    aggregated = make_empty_result()

    for row in rows:
        raw = row.get("raw_response_text")
        parsed = parse_raw_response(raw)
        if not parsed:
            # skip rows that couldn't be parsed
            continue

        for dim, sentiment_map in parsed.items():
            if dim not in ALLOWED_DIMENSIONS:
                # skip unknown dimensions
                continue
            if not isinstance(sentiment_map, dict):
                continue

            for sentiment, items in sentiment_map.items():
                if sentiment not in ALLOWED_SENTIMENTS:
                    continue
                if not isinstance(items, list):
                    continue

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    # ensure required fields exist; provide defaults if missing
                    cid = str(item.get("id", "")).strip()
                    pain = str(item.get("User_Pain_Point", "")).strip()
                    sugg = str(item.get("Actionable_Suggestion", "")).strip()
                    if not cid or not pain:
                        continue
                    if not sugg:
                        sugg = "无" if sentiment == "Positive" else ""

                    aggregated[dim][sentiment].append(
                        {"id": cid, "User_Pain_Point": pain, "Actionable_Suggestion": sugg}
                    )

    # prune empty dimensions
    pruned: dict[str, dict[str, list[dict[str, str]]]] = {}
    for dim in ALLOWED_DIMENSIONS:
        sentiments_with_items = {
            s: aggregated[dim][s] for s in ALLOWED_SENTIMENTS if aggregated[dim][s]
        }
        if sentiments_with_items:
            pruned[dim] = sentiments_with_items

    output_path.write_text(json.dumps(pruned, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate classified raw responses into per-dimension JSON")
    parser.add_argument("input", help="Path to classified_comments.raw.json")
    parser.add_argument("--output", help="Output path", default="classified_comments.aggregated.json")
    args = parser.parse_args()

    inp = Path(args.input)
    out = Path(args.output)
    if not inp.exists():
        raise SystemExit(f"input not found: {inp}")

    aggregate(inp, out)
    print("Wrote:", out)


if __name__ == "__main__":
    main()
