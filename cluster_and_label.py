from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_SPACE_RE = re.compile(r"[\s\u3000]+")
_TRIM_RE = re.compile(r"^[\s\-—_·,，。！？!?;；:：()（）\[\]{}<>《》\"'`~]+|[\s\-—_·,，。！？!?;；:：()（）\[\]{}<>《》\"'`~]+$")


def normalize_text(text: Any) -> str:
    if text is None:
        return ""
    value = str(text).strip().lower()
    if not value:
        return ""
    value = _SPACE_RE.sub(" ", value)
    value = _TRIM_RE.sub("", value)
    value = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _parse_raw_response(raw_response: Any) -> dict[str, Any] | None:
    if raw_response is None:
        return None
    if isinstance(raw_response, dict):
        return raw_response
    if not isinstance(raw_response, str):
        return None

    text = raw_response.strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
    except Exception:
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            return None
        try:
            parsed = json.loads(text[first : last + 1])
        except Exception:
            return None

    return parsed if isinstance(parsed, dict) else None


def collect_items(rows: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return items

    for raw_record in rows:
        if not isinstance(raw_record, dict):
            continue

        request_comments = raw_record.get("request_comments")
        if not isinstance(request_comments, list):
            request_comments = []

        comment_map: dict[str, dict[str, str]] = {}
        for comment in request_comments:
            if not isinstance(comment, dict):
                continue
            comment_id = str(comment.get("id", "")).strip()
            if not comment_id:
                continue
            comment_map[comment_id] = {
                "source": str(comment.get("content", "")).strip(),
                "device": str(comment.get("device", "")).strip(),
            }

        parsed = _parse_raw_response(raw_record.get("raw_response_text"))
        if not parsed:
            continue

        for dimension, sentiment_map in parsed.items():
            if not isinstance(sentiment_map, dict):
                continue
            for sentiment, result_items in sentiment_map.items():
                if not isinstance(result_items, list):
                    continue
                for item in result_items:
                    if not isinstance(item, dict):
                        continue
                    comment_id = str(item.get("id", "")).strip()
                    pain = str(item.get("User_Pain_Point", "")).strip()
                    suggestion = str(item.get("Actionable_Suggestion", "")).strip()
                    if not comment_id or not pain:
                        continue

                    source_info = comment_map.get(comment_id, {})
                    source = source_info.get("source", "") or pain
                    device = source_info.get("device", "")

                    items.append(
                        {
                            "id": comment_id,
                            "dimension": str(dimension),
                            "sentiment": str(sentiment),
                            "pain": pain,
                            "suggestion": suggestion,
                            "source": source,
                            "source_normalized": normalize_text(source),
                            "device": device,
                        }
                    )

    return items


def load_classified_raw(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("classified raw file must contain a JSON array")
    return data
