#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cluster_and_label import collect_items, normalize_text
from llm_client import LLMClient


SYSTEM_PROMPT = """# Role
你是一个资深的鸿蒙（HarmonyOS）应用产品分析与评论聚类专家。

# Task
你会收到某一个“核心维度 + 情感倾向”下的一批评论条目。每个条目已经是原始长评论拆出来的单条问题或赞赏点。
你的任务是把这些条目按“同一底层问题”聚成若干簇。

# Important Rules
1. 必须把“同一个根因、不同表述”的条目合并到同一个簇。
2. 尤其要合并这些情况：
   - 功能名称相同但说法不同：例如“沉浸光感 / 底部光感 / 光感”
   - 机型差异、版本差异、是否更新、是否适配、是否独占，只要根因相同就要合并
   - 不同场景下的同类体验问题，只要都指向同一个根因就要合并
3. 如果一条输入明显包含多个独立问题，请拆成多个簇。
4. 每个输入条目必须且只能出现在一个簇里。
5. 你应该尽量使用更少的簇，但不能牺牲根因一致性。

# Output Format
只输出一个合法 JSON 对象，不要输出 markdown，不要输出解释文字。
格式必须是：
{
  "clusters": [
    {
      "cluster_name": "短中文簇名",
      "canonical_issue": "一句话描述该簇的统一问题",
      "member_item_ids": ["item_1", "item_2"]
    }
  ]
}

# Hard Constraints
1. `member_item_ids` 必须使用输入里的 `item_id`。
2. 所有输入 `item_id` 必须被且仅被分配一次。
3. 不允许遗漏任何输入条目，也不允许把同一个 `item_id` 放进多个簇。
4. `cluster_name` 要简短，最好是 4 到 12 个汉字。`cluster_name` 应尽量反映簇的根因而不是单一机型或临时表现。
5. `canonical_issue` 要尽量抽象到根因层级，例如“沉浸光感功能适配不全”。`canonical_issue` 应作为生成或选择 `cluster_name` 的首选依据，若 `cluster_name` 过于专有（例如仅包含机型名或推送场景），请使用 `canonical_issue` 的精简形式作为展示名。
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cluster comments with an LLM.")
    parser.add_argument(
        "--src",
        default=Path("com.xingin.xhs_hos/classified_comments.raw.json"),
        type=Path,
        help="Path to classified_comments.raw.json.",
    )
    parser.add_argument(
        "--out",
        default=Path("com.xingin.xhs_hos/clusters_preview_llm.json"),
        type=Path,
        help="Path to write the LLM cluster preview JSON.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=18,
        help="Maximum number of deduped items per LLM prompt bucket.",
    )
    return parser.parse_args()


def dedupe_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for index, item in enumerate(items):
        normalized_source = item.get("source_normalized") or normalize_text(item.get("source", ""))
        key = (item["dimension"], item["sentiment"], normalize_text(item["pain"] or normalized_source))
        if key in seen:
            continue
        seen.add(key)
        copied = dict(item)
        copied["item_id"] = f"item_{index}"
        copied["source_normalized"] = normalized_source
        deduped.append(copied)
    return deduped


def group_items(items: List[Dict[str, Any]]) -> Dict[tuple[str, str], List[Dict[str, Any]]]:
    grouped: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[(item["dimension"], item["sentiment"])].append(item)
    return grouped


def build_bucket_prompt(dimension: str, sentiment: str, bucket_items: List[Dict[str, Any]]) -> str:
    prompt_items = []
    for item in bucket_items:
        prompt_items.append(
            {
                "item_id": item["item_id"],
                "comment_id": item["id"],
                "pain": item.get("pain", ""),
                "suggestion": item.get("suggestion", ""),
                "source": item.get("source", ""),
                "source_normalized": item.get("source_normalized", ""),
                "device": item.get("device", ""),
            }
        )

    payload = {
        "dimension": dimension,
        "sentiment": sentiment,
        "items": prompt_items,
    }
    return (
        f"# Bucket\n"
        f"dimension: {dimension}\n"
        f"sentiment: {sentiment}\n\n"
        f"# Input JSON\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def extract_json_text(raw_text: str) -> str:
    stripped = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return stripped[first_brace : last_brace + 1].strip()

    return stripped


def parse_bucket_result(raw_text: str) -> dict[str, Any]:
    parsed = json.loads(extract_json_text(raw_text))
    if not isinstance(parsed, dict):
        raise ValueError("LLM output must be a JSON object")
    clusters = parsed.get("clusters")
    if not isinstance(clusters, list):
        raise ValueError("LLM output must contain a clusters array")
    return parsed


def repair_bucket_result(
    client: LLMClient,
    dimension: str,
    sentiment: str,
    bucket_items: List[Dict[str, Any]],
    raw_text: str,
) -> dict[str, Any] | None:
    repair_prompt = (
        f"请将下面这个 bucket 的聚类结果修复成合法 JSON，必须保留输入中的 item_id，且每个 item_id 只能出现一次。\n"
        f"dimension: {dimension}\n"
        f"sentiment: {sentiment}\n"
        f"原始输出如下：\n{raw_text}\n\n"
        f"输入条目如下：\n{json.dumps(bucket_items, ensure_ascii=False, indent=2)}"
    )
    try:
        repaired = client.chat_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=repair_prompt,
            temperature=0,
        )
        return parse_bucket_result(repaired.content)
    except Exception:
        return None


def validate_bucket_clusters(
    clusters: List[Dict[str, Any]],
    bucket_items: List[Dict[str, Any]],
) -> tuple[bool, list[str]]:
    valid_item_ids = {item["item_id"] for item in bucket_items}
    seen: set[str] = set()
    errors: list[str] = []

    for index, cluster in enumerate(clusters):
        if not isinstance(cluster, dict):
            errors.append(f"cluster_{index}: not an object")
            continue

        member_item_ids = cluster.get("member_item_ids")
        if not isinstance(member_item_ids, list) or not member_item_ids:
            errors.append(f"cluster_{index}: invalid member_item_ids")
            continue

        for item_id in member_item_ids:
            if not isinstance(item_id, str) or item_id not in valid_item_ids:
                errors.append(f"cluster_{index}: invalid item_id {item_id!r}")
                continue
            if item_id in seen:
                errors.append(f"cluster_{index}: duplicate item_id {item_id}")
            seen.add(item_id)

        cluster_name = str(cluster.get("cluster_name", "")).strip()
        canonical_issue = str(cluster.get("canonical_issue", "")).strip()
        if not cluster_name:
            errors.append(f"cluster_{index}: empty cluster_name")
        if not canonical_issue:
            errors.append(f"cluster_{index}: empty canonical_issue")

    missing = valid_item_ids - seen
    if missing:
        errors.append(f"missing_item_ids: {sorted(missing)}")

    return not errors, errors


def auto_repair_clusters(
    clusters: List[Dict[str, Any]], bucket_items: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], List[str]]:
    """Attempt to automatically repair common issues in LLM clusters.

    - Remove duplicate `member_item_ids` occurrences (keep first occurrence).
    - Discard invalid item_ids not present in the bucket.
    - Create singleton clusters for any missing item_ids.

    Returns (repaired_clusters, warnings).
    """
    valid_item_ids = {item["item_id"] for item in bucket_items}
    seen: set[str] = set()
    repaired: list[Dict[str, Any]] = []
    warnings: list[str] = []
    item_lookup = {item["item_id"]: item for item in bucket_items}

    # First pass: clean clusters, remove duplicates/unknowns
    for idx, cluster in enumerate(clusters):
        raw_ids = cluster.get("member_item_ids") or []
        if not isinstance(raw_ids, list):
            warnings.append(f"cluster_{idx}: member_item_ids not a list, skipping")
            continue

        new_ids: list[str] = []
        for item_id in raw_ids:
            if not isinstance(item_id, str):
                warnings.append(f"cluster_{idx}: non-string item_id {item_id!r}, skipped")
                continue
            if item_id not in valid_item_ids:
                warnings.append(f"cluster_{idx}: unknown item_id {item_id}, skipped")
                continue
            if item_id in seen:
                warnings.append(f"cluster_{idx}: duplicate item_id {item_id} removed")
                continue
            seen.add(item_id)
            new_ids.append(item_id)

        if not new_ids:
            warnings.append(f"cluster_{idx}: emptied after dedupe/validation, dropped")
            continue

        repaired_cluster = dict(cluster)
        repaired_cluster["member_item_ids"] = new_ids
        repaired.append(repaired_cluster)

    # Attempt to assign missing items to existing clusters using simple token overlap
    missing = sorted(list(valid_item_ids - seen))
    if missing and repaired:
        # Build representative text for each repaired cluster
        cluster_reps: list[str] = []
        for c in repaired:
            rep = " ".join(
                [str(c.get("canonical_issue", "")), str(c.get("cluster_name", ""))]
            ).lower()
            cluster_reps.append(rep)

        for missing_id in missing[:]:
            item = item_lookup.get(missing_id, {})
            text = " ".join(
                [str(item.get("pain", "")), str(item.get("source", "")), str(item.get("suggestion", ""))]
            ).lower()
            words = set(w for w in re.split(r"\W+", text) if w)

            best_idx = -1
            best_score = 0
            for i, rep in enumerate(cluster_reps):
                rep_words = set(w for w in re.split(r"\W+", rep) if w)
                score = len(words & rep_words)
                if score > best_score:
                    best_score = score
                    best_idx = i

            if best_idx >= 0 and best_score > 0:
                # assign to best matching existing cluster
                repaired[best_idx]["member_item_ids"].append(missing_id)
                warnings.append(f"missing item assigned to existing cluster {best_idx}: {missing_id}")
                seen.add(missing_id)
            else:
                # create singleton cluster as fallback
                warnings.append(f"missing item assigned to singleton cluster: {missing_id}")
                repaired.append(
                    {
                        "cluster_name": "(auto) 单项簇",
                        "canonical_issue": "(auto) 未匹配到其它簇的条目",
                        "member_item_ids": [missing_id],
                    }
                )

    else:
        # No repaired clusters to try merging into, just create singletons
        for missing_id in missing:
            warnings.append(f"missing item assigned to singleton cluster: {missing_id}")
            repaired.append(
                {
                    "cluster_name": "(auto) 单项簇",
                    "canonical_issue": "(auto) 未匹配到其它簇的条目",
                    "member_item_ids": [missing_id],
                }
            )

    return repaired, warnings


def build_cluster_preview_llm(items: List[Dict[str, Any]], batch_size: int) -> Dict[str, Any]:
    client = LLMClient()
    deduped = dedupe_items(items)
    grouped = group_items(deduped)

    preview: Dict[str, Any] = {
        "n_items": len(items),
        "n_items_deduped": len(deduped),
    }

    cluster_global_id = 0

    for (dimension, sentiment), bucket_items in grouped.items():
        dimension_bucket = preview.setdefault(dimension, {})
        sentiment_bucket = dimension_bucket.setdefault(sentiment.lower(), {"clusters": []})

        bucket_clusters: list[dict[str, Any]] = []
        for start in range(0, len(bucket_items), batch_size):
            chunk_items = bucket_items[start : start + batch_size]
            user_prompt = build_bucket_prompt(dimension, sentiment, chunk_items)
            result = client.chat_completion(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0,
            )
            try:
                parsed = parse_bucket_result(result.content)
            except Exception:
                parsed = repair_bucket_result(client, dimension, sentiment, chunk_items, result.content)
                if not parsed:
                    raise RuntimeError(
                        f"Failed to parse LLM clustering result for {dimension}/{sentiment}"
                    )

            clusters = parsed.get("clusters", [])
            if not isinstance(clusters, list):
                raise RuntimeError(f"Invalid clusters array for {dimension}/{sentiment}")
            # Try an automatic repair first to handle duplicate/missing ids produced by the LLM
            clusters, auto_warnings = auto_repair_clusters(clusters, chunk_items)
            if auto_warnings:
                print(f"LLM auto-repair warnings for {dimension}/{sentiment}: {auto_warnings}")

            ok, errors = validate_bucket_clusters(clusters, chunk_items)
            if not ok:
                repaired = repair_bucket_result(client, dimension, sentiment, chunk_items, json.dumps(parsed, ensure_ascii=False))
                if not repaired:
                    raise RuntimeError(
                        f"LLM clustering validation failed for {dimension}/{sentiment}: {errors}"
                    )
                clusters = repaired.get("clusters", [])
                ok, errors = validate_bucket_clusters(clusters, chunk_items)
                if not ok:
                    raise RuntimeError(
                        f"LLM clustering repair failed for {dimension}/{sentiment}: {errors}"
                    )

            item_lookup = {item["item_id"]: item for item in chunk_items}
            for cluster in clusters:
                member_item_ids = [str(item_id) for item_id in cluster.get("member_item_ids", [])]
                member_items = [item_lookup[item_id] for item_id in member_item_ids]

                sample_members = [
                    {
                        "id": item["id"],
                        "pain": item["pain"],
                        "suggestion": item["suggestion"],
                        "source": item["source"],
                        "device": item["device"],
                    }
                    for item in member_items[:5]
                ]

                # Prefer a root-cause based display name. Use `cluster_name` when it's concise
                # and root-cause oriented; otherwise fall back to a short form of `canonical_issue`.
                raw_name = str(cluster.get("cluster_name", "")).strip()
                canonical_text = str(cluster.get("canonical_issue", "")).strip()
                display_name = raw_name
                # Heuristic: if canonical mentions '适配' (adaptation) prefer it as display name,
                # or if the raw name is missing/empty, fall back to canonical_issue.
                if (not raw_name) or ("适配" in canonical_text and "适配" not in raw_name):
                    # shorten canonical to a concise phrase (<=12 chars) for display
                    display_name = canonical_text[:12]

                bucket_clusters.append(
                    {
                        "cluster_id": f"{cluster_global_id}",
                        "cluster_name": display_name,
                        "canonical_issue": canonical_text,
                        "size": len(member_items),
                        "sample_members": sample_members,
                        "member_ids": [item["id"] for item in member_items],
                    }
                )
                cluster_global_id += 1

        sentiment_bucket["clusters"] = bucket_clusters

    preview["n_clusters"] = cluster_global_id
    return preview


def main() -> None:
    args = parse_args()

    if not args.src.exists():
        print("input not found:", args.src)
        return

    rows = json.loads(args.src.read_text(encoding="utf-8"))
    items = collect_items(rows)
    if not items:
        print("no items parsed")
        return

    try:
        preview = build_cluster_preview_llm(items, args.batch_size)
    except Exception as exc:
        print(str(exc))
        return

    args.out.write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote preview to", args.out)


if __name__ == "__main__":
    main()