from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

from llm_client import LLMClient


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
SYSTEM_PROMPT = """# Role
你是一个资深的鸿蒙（HarmonyOS）应用产品经理与数据分析专家。

# Task
我将提供一个包含多条用户评论的 JSON 数组。请逐条分析这些评论，提取其包含的痛点或赞赏点。
请完全舍弃具体的子类别（Sub_Category），直接按“核心维度”进行一级分组，并在该维度下按“情感倾向（Sentiment）”进行二级分组。若一条长评论包含多个问题，请拆解并分别放入对应的层级中。

# Classification Schema
1. 核心维度 (一级 Key)：必须从以下列表中选择 [功能体验, 系统与机型适配, 稳定性与性能, UI与交互, 运营与规则, 体验赞赏, 内容生态]
2. 情感倾向 (二级 Key)：必须从以下列表中选择 [Negative, Positive, Neutral]

# Output Format
严格输出一个合法的 JSON 对象，不包含任何 markdown 标记或解释文字。结构必须是：维度 -> 情感 -> 数组。
数组内每个对象必须包含字段：id、User_Pain_Point、Actionable_Suggestion。

# Hard Rules
1. 必须保留输入中的 id。
2. 一条长评论可以拆成多个结果项，但每个结果项都必须使用原评论 id。
3. 不允许输出维度枚举之外的值。
4. 不允许输出情感枚举之外的值。
5. 如果是正向赞赏，Actionable_Suggestion 固定写“无”。
6. 如果没有可提取内容，请返回空数组，不要编造。"""
REPAIR_SYSTEM_PROMPT = """你是一个 JSON 修复助手。
你会收到一段本应为分类结果的文本。请将其修复为一个合法 JSON 对象。
只输出 JSON 对象本身，不要输出解释，不要新增原文中不存在的评论 id。
维度只能是 [功能体验, 系统与机型适配, 稳定性与性能, UI与交互, 运营与规则, 体验赞赏, 内容生态]。
情感只能是 [Negative, Positive, Neutral]。
数组项必须包含字段：id、User_Pain_Point、Actionable_Suggestion。"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze app comments with an LLM.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--package", help="Only analyze the given package directory.")
    group.add_argument(
        "--all",
        action="store_true",
        help="Analyze all package directories that contain comments.json.",
    )
    parser.add_argument(
        "--root",
        default=Path(__file__).resolve().parent,
        type=Path,
        help="Project root directory. Defaults to the current repository root.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of comments to send per batch.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only analyze the first N comments. Useful for smoke checks.",
    )
    return parser.parse_args()


def make_empty_result() -> dict[str, dict[str, list[dict[str, str]]]]:
    return {
        dimension: {sentiment: [] for sentiment in ALLOWED_SENTIMENTS}
        for dimension in ALLOWED_DIMENSIONS
    }


def iter_comment_directories(root: Path) -> Iterable[Path]:
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "comments.json").exists():
            yield child


def resolve_target_directories(root: Path, package: str | None, all_packages: bool) -> list[Path]:
    if package:
        target_dir = root / package
        comments_path = target_dir / "comments.json"
        if not comments_path.exists():
            raise FileNotFoundError(f"comments.json not found for package: {package}")
        return [target_dir]

    if all_packages:
        directories = list(iter_comment_directories(root))
        if not directories:
            raise FileNotFoundError("No package directories containing comments.json were found")
        return directories

    raise ValueError("Either --package or --all must be provided")


def load_comments(package_dir: Path) -> list[dict[str, str]]:
    package_name = package_dir.name
    comments_path = package_dir / "comments.json"
    with comments_path.open("r", encoding="utf-8") as file:
        comments_data = json.load(file)

    if not isinstance(comments_data, list):
        raise ValueError(f"{comments_path} must contain a JSON array")

    normalized_comments: list[dict[str, str]] = []
    for index, item in enumerate(comments_data, start=1):
        if not isinstance(item, dict):
            continue

        content = str(item.get("content", "")).strip()
        if not content:
            continue

        normalized_comments.append(
            {
                "id": f"{package_name}_{index}",
                "content": content,
                "device": str(item.get("device", "")).strip(),
            }
        )

    return normalized_comments


def chunked(items: list[dict[str, str]], batch_size: int) -> Iterable[list[dict[str, str]]]:
    if batch_size <= 0:
        raise ValueError("--batch-size must be greater than 0")

    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def build_user_prompt(comments_batch: list[dict[str, str]]) -> str:
    input_json = json.dumps(comments_batch, ensure_ascii=False, indent=2)
    return f"# Input Data\n{input_json}"


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


def parse_model_json(raw_text: str) -> dict[str, Any]:
    json_text = extract_json_text(raw_text)
    parsed = json.loads(json_text)
    if not isinstance(parsed, dict):
        raise ValueError("Model output must be a JSON object")
    return parsed


def repair_model_output(
    client: LLMClient,
    raw_text: str,
    batch_ids: list[str],
) -> tuple[dict[str, Any] | None, str | None]:
    repair_prompt = (
        "请将下面文本修复成合法 JSON 对象，并保留这些有效评论 id："
        f"{json.dumps(batch_ids, ensure_ascii=False)}\n\n"
        f"原始文本如下：\n{raw_text}"
    )
    try:
        repair_result = client.chat_completion(
            system_prompt=REPAIR_SYSTEM_PROMPT,
            user_prompt=repair_prompt,
            temperature=0,
        )
        return parse_model_json(repair_result.content), repair_result.content
    except Exception:
        return None, None


def validate_result_object(
    result_object: dict[str, Any],
    valid_ids: set[str],
) -> tuple[dict[str, dict[str, list[dict[str, str]]]], list[dict[str, Any]]]:
    normalized = make_empty_result()
    errors: list[dict[str, Any]] = []

    for dimension, sentiment_map in result_object.items():
        if dimension not in ALLOWED_DIMENSIONS:
            errors.append(
                {"type": "invalid_dimension", "dimension": dimension}
            )
            continue

        if not isinstance(sentiment_map, dict):
            errors.append(
                {"type": "invalid_sentiment_map", "dimension": dimension}
            )
            continue

        for sentiment, items in sentiment_map.items():
            if sentiment not in ALLOWED_SENTIMENTS:
                errors.append(
                    {
                        "type": "invalid_sentiment",
                        "dimension": dimension,
                        "sentiment": sentiment,
                    }
                )
                continue

            if not isinstance(items, list):
                errors.append(
                    {
                        "type": "invalid_items",
                        "dimension": dimension,
                        "sentiment": sentiment,
                    }
                )
                continue

            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    errors.append(
                        {
                            "type": "invalid_item",
                            "dimension": dimension,
                            "sentiment": sentiment,
                            "index": index,
                        }
                    )
                    continue

                comment_id = str(item.get("id", "")).strip()
                pain_point = str(item.get("User_Pain_Point", "")).strip()
                suggestion = str(item.get("Actionable_Suggestion", "")).strip()

                if not comment_id or comment_id not in valid_ids:
                    errors.append(
                        {
                            "type": "invalid_id",
                            "dimension": dimension,
                            "sentiment": sentiment,
                            "index": index,
                            "id": comment_id,
                        }
                    )
                    continue

                if not pain_point:
                    errors.append(
                        {
                            "type": "missing_pain_point",
                            "dimension": dimension,
                            "sentiment": sentiment,
                            "index": index,
                            "id": comment_id,
                        }
                    )
                    continue

                if not suggestion:
                    suggestion = "无" if sentiment == "Positive" else "待补充建议"

                normalized[dimension][sentiment].append(
                    {
                        "id": comment_id,
                        "User_Pain_Point": pain_point,
                        "Actionable_Suggestion": suggestion,
                    }
                )

    return normalized, errors


def merge_results(
    merged_result: dict[str, dict[str, list[dict[str, str]]]],
    batch_result: dict[str, dict[str, list[dict[str, str]]]],
) -> None:
    for dimension in ALLOWED_DIMENSIONS:
        for sentiment in ALLOWED_SENTIMENTS:
            merged_result[dimension][sentiment].extend(batch_result[dimension][sentiment])


def write_json_file(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def prune_empty_entries(
    result_data: dict[str, dict[str, list[dict[str, str]]]]
) -> dict[str, dict[str, list[dict[str, str]]]]:
    pruned: dict[str, dict[str, list[dict[str, str]]]] = {}
    for dimension in ALLOWED_DIMENSIONS:
        sentiments_with_items = {
            sentiment: result_data[dimension][sentiment]
            for sentiment in ALLOWED_SENTIMENTS
            if result_data[dimension][sentiment]
        }
        if sentiments_with_items:
            pruned[dimension] = sentiments_with_items
    return pruned


def analyze_package(
    package_dir: Path,
    client: LLMClient,
    batch_size: int,
    limit: int | None = None,
) -> None:
    package_name = package_dir.name
    comments = load_comments(package_dir)
    if limit is not None:
        if limit <= 0:
            raise ValueError("--limit must be greater than 0")
        comments = comments[:limit]
    merged_result = make_empty_result()
    raw_records: list[dict[str, Any]] = []
    error_records: list[dict[str, Any]] = []

    print(f"开始处理应用: {package_name}，共 {len(comments)} 条评论")

    for batch_index, batch_comments in enumerate(chunked(comments, batch_size), start=1):
        batch_ids = [item["id"] for item in batch_comments]
        user_prompt = build_user_prompt(batch_comments)
        raw_text = ""
        parsed_object: dict[str, Any] | None = None
        repaired_text: str | None = None

        try:
            completion = client.chat_completion(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            raw_text = completion.content
            parsed_object = parse_model_json(raw_text)
        except Exception as exc:
            error_records.append(
                {
                    "package": package_name,
                    "batch_index": batch_index,
                    "batch_ids": batch_ids,
                    "stage": "request_or_parse",
                    "error": str(exc),
                }
            )

        if parsed_object is None and raw_text:
            repaired_object, repaired_text = repair_model_output(client, raw_text, batch_ids)
            parsed_object = repaired_object
            if parsed_object is None:
                error_records.append(
                    {
                        "package": package_name,
                        "batch_index": batch_index,
                        "batch_ids": batch_ids,
                        "stage": "repair",
                        "error": "Failed to repair model output into valid JSON",
                    }
                )
        elif parsed_object is None:
            error_records.append(
                {
                    "package": package_name,
                    "batch_index": batch_index,
                    "batch_ids": batch_ids,
                    "stage": "repair",
                    "error": "Skipped repair because no model output was returned",
                }
            )

        raw_records.append(
            {
                "package": package_name,
                "batch_index": batch_index,
                "batch_ids": batch_ids,
                "request_comments": batch_comments,
                "raw_response_text": raw_text,
                "repair_response_text": repaired_text,
            }
        )

        if parsed_object is None:
            print(f"  批次 {batch_index}: 解析失败，已记录错误")
            continue

        batch_result, validation_errors = validate_result_object(parsed_object, set(batch_ids))
        merge_results(merged_result, batch_result)

        for validation_error in validation_errors:
            validation_error["package"] = package_name
            validation_error["batch_index"] = batch_index
            validation_error["batch_ids"] = batch_ids
            validation_error["stage"] = "validate"
            error_records.append(validation_error)

        valid_count = sum(
            len(batch_result[dimension][sentiment])
            for dimension in ALLOWED_DIMENSIONS
            for sentiment in ALLOWED_SENTIMENTS
        )
        print(f"  批次 {batch_index}: 完成，落入结果 {valid_count} 条")

    result_path = package_dir / "classified_comments.json"
    raw_path = package_dir / "classified_comments.raw.json"
    error_path = package_dir / "classified_comments.errors.json"

    write_json_file(result_path, prune_empty_entries(merged_result))
    write_json_file(raw_path, raw_records)
    write_json_file(error_path, error_records)

    print(f"结果已保存: {result_path}")


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    target_directories = resolve_target_directories(root, args.package, args.all)
    client = LLMClient()

    for package_dir in target_directories:
        analyze_package(package_dir, client, args.batch_size, args.limit)


if __name__ == "__main__":
    main()
