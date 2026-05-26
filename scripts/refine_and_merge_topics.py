from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from llm_client import LLMClient

SYSTEM_PROMPT = """# Role
你是一个资深的应用评论分析专家，擅长话题归纳与标签标准化。

# Task
我会给你一组已经初步聚类的話题簇。每个簇包含一个原始名称、一个核心问题的描述。
你的任务是：
1. **二次合并**：识别出描述同一类根因、或语义高度相近的簇，并将它们合并。
2. **标签标准化**：为合并后的新簇生成一个专业、中性、简练的“标准话题名称”和“核心根因描述”。

# Rules
- 必须保留原始簇中的所有 `member_ids`。
- 标准话题名称应控制在 4-10 个汉字，避免过于口语化或包含特定机型。
- 如果两个话题只是表述略有不同（例如“闪退”与“崩溃”），必须合并。
- 输出必须是严格的 JSON 格式。

# Output Format
{
  "clusters": [
    {
      "topic_name": "标准话题名称",
      "canonical_issue": "核心根因的详细描述",
      "merged_from_ids": ["v1_cluster_0", "v1_cluster_1"],
      "member_ids": ["uuid_1", "uuid_2", "uuid_3"]
    }
  ]
}
"""

def parse_args():
    parser = argparse.ArgumentParser(description="Second-stage cluster merging and labeling via LLM.")
    parser.add_argument("--src", required=True, type=Path, help="Path to clusters_preview_llm.json")
    parser.add_argument("--out", type=Path, help="Output path for refined clusters.")
    parser.add_argument("--batch-size", type=int, default=15, help="Number of clusters to process per LLM call.")
    return parser.parse_args()

def extract_clusters_for_merging(preview_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    extracted = []
    # 遍历所有维度和情感
    for dimension, sentiments in preview_data.items():
        if not isinstance(sentiments, dict): continue
        for sentiment, content in sentiments.items():
            if not isinstance(content, dict): continue
            clusters = content.get("clusters", [])
            for c in clusters:
                extracted.append({
                    "v1_cluster_id": c["cluster_id"],
                    "dimension": dimension,
                    "sentiment": sentiment,
                    "original_name": c["cluster_name"],
                    "original_issue": c["canonical_issue"],
                    "member_ids": c["member_ids"],
                    "size": c["size"]
                })
    return extracted

def build_merge_prompt(clusters: List[Dict[str, Any]]) -> str:
    input_data = []
    for c in clusters:
        input_data.append({
            "id": c["v1_cluster_id"],
            "name": c["original_name"],
            "issue": c["original_issue"],
            "item_count": c["size"]
        })
    return f"# Input Clusters\n{json.dumps(input_data, ensure_ascii=False, indent=2)}"

def main():
    args = parse_args()
    if not args.out:
        args.out = args.src.parent / "clusters_refined_llm.json"

    with args.src.open("r", encoding="utf-8") as f:
        preview_data = json.load(f)

    all_v1_clusters = extract_clusters_for_merging(preview_data)
    if not all_v1_clusters:
        print("No clusters found to merge.")
        return

    client = LLMClient()
    # 简单起见，这里按维度+情感分组处理，或者全量处理（若簇数量不多）
    # 目前先实现一个全量的逻辑，如果簇太多再考虑 chunked
    
    print(f"Loaded {len(all_v1_clusters)} clusters for refinement.")
    
    # 将簇按 (维度, 情感) 分组进行二次合并
    grouped_v1 = {}
    for c in all_v1_clusters:
        key = (c["dimension"], c["sentiment"])
        grouped_v1.setdefault(key, []).append(c)

    final_output = {
        "metadata": {
            "source": str(args.src),
            "v1_items_count": preview_data.get("n_items"),
            "v1_clusters_count": len(all_v1_clusters)
        },
        "refined_results": {}
    }

    total_new_clusters = 0
    for (dim, sent), clusters in grouped_v1.items():
        print(f"Processing {dim} - {sent} ({len(clusters)} clusters)...")
        
        user_prompt = build_merge_prompt(clusters)
        response = client.chat_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0
        )
        
        try:
            # 使用简单的正则或 json.loads 提取
            raw_content = response.content
            match = re.search(r'\{.*\}', raw_content, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
            else:
                parsed = json.loads(raw_content)
                
            refined_clusters = parsed.get("clusters", [])
            
            # 回填 member_ids
            v1_lookup = {c["v1_cluster_id"]: c["member_ids"] for c in clusters}
            for rc in refined_clusters:
                merged_ids = []
                for v1_id in rc.get("merged_from_ids", []):
                    merged_ids.extend(v1_lookup.get(v1_id, []))
                rc["member_ids"] = list(set(merged_ids))
                rc["size"] = len(rc["member_ids"])
                total_new_clusters += 1
            
            final_output["refined_results"].setdefault(dim, {})[sent] = refined_clusters
            
        except Exception as e:
            print(f"Error processing {dim}-{sent}: {e}")
            # 容错：保留原样
            final_output["refined_results"].setdefault(dim, {})[sent] = clusters

    final_output["total_refined_clusters"] = total_new_clusters
    args.out.write_text(json.dumps(final_output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Successfully refined clusters into {total_new_clusters} topics. Saved to {args.out}")

if __name__ == "__main__":
    main()
