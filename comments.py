# comment.py

# 标准库
import re
import json
import time
from pathlib import Path

# 第三方库
from lxml import etree

# 项目内库
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    COMMENT_LIST_BASE, COMMENT_ITEMS,
    COMMENT_USERNAME, COMMENT_RATING,
    COMMENT_TEXT, COMMENT_META,
)
from hmdriver2.driver import Driver
from hmdriver2.proto import Bounds
from hmdriver2.utils import parse_bounds
from xml_utils import json2xml


def parse_comment(node: etree._Element) -> dict:
    """Parse a single comment ListItem node into a dict."""

    def get_text(xpath):
        result = node.xpath(xpath)
        if result:
            return result[0].attrib.get("text", "").strip()
        return ""

    meta_text = get_text(COMMENT_META)
    parts = [p.strip() for p in meta_text.split("|") if p.strip()]

    date     = ""
    location = ""
    device   = ""

    if len(parts) == 3:
        date, location, device = parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        # second part is device, no location
        date, device = parts[0], parts[1]
    elif len(parts) == 1:
        date = parts[0]

    return {
        "username": get_text(COMMENT_USERNAME),
        "rating":   get_text(COMMENT_RATING),
        "content":  get_text(COMMENT_TEXT),
        "date":     date,
        "location": location,
        "device":   device,
    }


def scrape_comments(driver: Driver, max_swipes: int = 50, wait: float = 2.0) -> list[dict]:
    all_comments = []
    seen_keys = set()

    def collect(xml):
        nodes = xml.xpath(COMMENT_ITEMS)
        new_count = 0
        for node in nodes:
            comment = parse_comment(node)

            # skip incomplete comments
            if not comment["username"] or not comment["content"] or not comment["date"]:
                continue
            key = f"{comment['username']}_{comment['date']}_{comment['content'][:20]}"
            if key in seen_keys:
                continue

            seen_keys.add(key)
            all_comments.append(comment)
            new_count += 1
            print(f"  [{len(all_comments)}] {comment['username']} | {comment['rating']} | {comment['date']} | {comment['content'][:30]}...")
        return new_count

    # collect first screen before any swipe
    layout = driver.dump_hierarchy()
    xml = json2xml(layout)
    collect(xml)

    for i in range(max_swipes):
        driver.swipe(
            SCREEN_WIDTH // 2, SCREEN_HEIGHT * 0.8,
            SCREEN_WIDTH // 2, SCREEN_HEIGHT * 0.3,
            speed=800
        )
        time.sleep(wait)

        layout = driver.dump_hierarchy()
        xml = json2xml(layout)
        new_count = collect(xml)

        print(f"Swipe {i+1}/{max_swipes} — found {new_count} new (total: {len(all_comments)})")

        if new_count == 0:
            print("No new comments found, reached end of list.")
            break

    return all_comments


def save_comments(comments: list[dict], path: str = "comments.json"):
    """Save comments to a JSON file."""
    output = Path(path)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(comments, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(comments)} comments to {output.resolve()}")