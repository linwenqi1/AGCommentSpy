# comment.py

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from lxml import etree

from config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    COMMENT_LIST_BASE,
    COMMENT_ITEMS,
    COMMENT_USERNAME,
    COMMENT_RATING,
    COMMENT_TEXT,
    COMMENT_META,
    COMMENT_EXPAND_BUTTON,
)
from hmdriver2.driver import Driver
from hmdriver2.proto import Bounds
from hmdriver2.utils import parse_bounds
from xml_utils import json2xml


def normalize_date(date_str: str) -> str:
    date_str = date_str.strip()
    now = datetime.now()
    
    if "分钟前" in date_str:
        match = re.search(r'(\d+)\s*分钟前', date_str)
        if match:
            mins = int(match.group(1))
            return (now - timedelta(minutes=mins)).strftime("%m/%d")
    elif "小时前" in date_str:
        match = re.search(r'(\d+)\s*小时前', date_str)
        if match:
            hours = int(match.group(1))
            return (now - timedelta(hours=hours)).strftime("%m/%d")
    elif "昨天" in date_str:
        return (now - timedelta(days=1)).strftime("%m/%d")
    elif "前天" in date_str:
        return (now - timedelta(days=2)).strftime("%m/%d")
    
    # Extract existing MM/DD or MM-DD formats (e.g. "04/30", "04-30")
    match = re.search(r'(?:20\d{2}[/-])?(\d{2})[/-](\d{2})', date_str)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
        
    return date_str


def parse_comment(node: etree._Element) -> dict:
    """Parse a single comment ListItem node into a dict."""

    def get_text(xpath):
        result = node.xpath(xpath)
        if result:
            return result[0].attrib.get("text", "").strip()
        return ""

    meta_text = get_text(COMMENT_META)
    parts = [p.strip() for p in meta_text.split("|") if p.strip()]

    date = ""
    location = ""
    device = ""

    if len(parts) >= 3:
        date, location, device = parts[0], parts[1], " | ".join(parts[2:])
    elif len(parts) == 2:
        date, device = parts[0], parts[1]
    elif len(parts) == 1:
        date = parts[0]

    return {
        "username": get_text(COMMENT_USERNAME),
        "rating": get_text(COMMENT_RATING),
        "content": get_text(COMMENT_TEXT),
        "date": normalize_date(date),
        "location": location,
        "device": device,
    }


def is_comment_complete(comment: dict) -> bool:
    return bool(comment.get("username") and comment.get("content") and comment.get("date"))


def merge_comment(existing: dict, incoming: dict) -> dict:
    merged = existing.copy()

    incoming_content = incoming.get("content", "")
    existing_content = merged.get("content", "")
    if incoming_content and len(incoming_content) > len(existing_content):
        merged["content"] = incoming_content

    for field in ("username", "rating", "date", "location", "device"):
        if not merged.get(field) and incoming.get(field):
            merged[field] = incoming[field]

    return merged


def is_in_bounds(inner: Bounds | None, outer: Bounds | None) -> bool:
    if inner is None or outer is None:
        return False
    center = inner.get_center()
    return outer.left <= center.x <= outer.right and outer.top <= center.y <= outer.bottom


def should_expand(node: etree._Element, list_bounds: Bounds | None) -> bool:
    bounds = parse_bounds(node.attrib.get("bounds", ""))
    if not is_in_bounds(bounds, list_bounds):
        return False

    return True


def expand_long_comments(
    driver: Driver,
    layout: dict | None = None,
    wait: float = 0.8,
    max_clicks: int = 8,
) -> tuple[dict, etree._Element, int]:
    if layout is None:
        layout = driver.dump_hierarchy()

    xml = json2xml(layout)
    list_nodes = xml.xpath(COMMENT_LIST_BASE)
    if not list_nodes:
        return layout, xml, 0

    list_bounds = parse_bounds(list_nodes[0].attrib.get("bounds", ""))
    candidates: list[Bounds] = []

    for node in xml.xpath(COMMENT_EXPAND_BUTTON):
        if not should_expand(node, list_bounds):
            continue

        bounds = parse_bounds(node.attrib.get("bounds", ""))
        if bounds is not None:
            candidates.append(bounds)

    if not candidates:
        return layout, xml, 0

    click_count = 0
    # Click from bottom to top so earlier clicks do not shift targets above them.
    for bounds in sorted(candidates, key=lambda item: item.top, reverse=True)[:max_clicks]:
        center = bounds.get_center()
        driver.click(center.x, center.y)
        click_count += 1
        time.sleep(wait)

    layout = driver.dump_hierarchy()
    return layout, json2xml(layout), click_count


def scrape_comments(driver: Driver, max_swipes: int = 50, wait: float = 2.0) -> list[dict]:
    all_comments: list[dict] = []
    comment_index_by_key: dict[str, int] = {}

    def collect(xml: etree._Element) -> tuple[int, int]:
        nodes = xml.xpath(COMMENT_ITEMS)
        new_count = 0
        updated_count = 0

        for node in nodes:
            comment = parse_comment(node)
            key = comment["content"][:20]
            if not key:
                continue

            index = comment_index_by_key.get(key)
            if index is None:
                comment_index_by_key[key] = len(all_comments)
                all_comments.append(comment)
                new_count += 1
                print(
                    f"  [{len(all_comments)}] {comment['username']} | "
                    f"{comment['rating']} | {comment['date']} | {comment['content'][:30]}..."
                )
                continue

            existing = all_comments[index]
            merged = merge_comment(existing, comment)
            if is_comment_complete(existing) and merged == existing:
                continue

            if merged != existing:
                all_comments[index] = merged
                updated_count += 1
                print(
                    f"  [update {index + 1}] {merged['username']} | "
                    f"{merged['rating']} | {merged['date']} | {merged['content'][:30]}..."
                )

        return new_count, updated_count

    layout = driver.dump_hierarchy()
    layout, xml, expand_count = expand_long_comments(driver, layout=layout, wait=min(wait, 1.0))
    if expand_count:
        print(f"Expanded {expand_count} long comment(s) on initial screen.")
    collect(xml)

    for i in range(max_swipes):
        driver.swipe(
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT * 0.8,
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT * 0.3,
            speed=800,
        )
        time.sleep(wait)

        layout = driver.dump_hierarchy()
        layout, xml, expand_count = expand_long_comments(driver, layout=layout, wait=min(wait, 1.0))
        if expand_count:
            print(f"Expanded {expand_count} long comment(s) after swipe {i + 1}.")

        new_count, updated_count = collect(xml)
        progress_count = new_count + updated_count

        print(
            f"Swipe {i + 1}/{max_swipes} - found {new_count} new, "
            f"updated {updated_count} (total: {len(all_comments)})"
        )

    return all_comments


def save_comments(comments: list[dict], path: str = "comments.json"):
    """Save comments to a JSON file."""
    output = Path(path)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(comments, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(comments)} comments to {output.resolve()}")
