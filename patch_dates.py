import os
import json
import re

def patch_comments(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        comments = json.load(f)
    
    current_year = 2026
    prev_month = None
    modified = False

    for comment in comments:
        date_str = comment.get("date", "")
        
        # 跳过看起来已经包含年份的日期（例如 2026/05/18 或 2026-05-18）
        if re.match(r'^20\d{2}[/-]', date_str):
            continue

        # 匹配 MM/DD 或 MM-DD 格式
        match = re.search(r'^(\d{2})[/-](\d{2})$', date_str)
        if match:
            month = int(match.group(1))
            
            # 如果是从较小月份突然变成较大月份（例如从 01月 变到 12月）
            # 说明按照时间倒序，我们跨年了
            if prev_month is not None and month > prev_month + 6:
                current_year -= 1
                
            prev_month = month
            
            # 补齐年份
            # 将 05/18 转换为 2026/05/18
            new_date = f"{current_year}/{date_str}"
            comment["date"] = new_date
            modified = True

    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(comments, f, ensure_ascii=False, indent=2)
        print(f"[OK] Patched {file_path}")
    else:
        print(f"[Skip] No changes needed for {file_path}")

def main():
    skip_dirs = {"com.xingin.xhs_hos"}
    
    # 遍历当前目录下的所有文件夹
    for item in os.listdir('.'):
        if os.path.isdir(item) and item.startswith("com."):
            if item in skip_dirs:
                print(f"[Skip] Ignored directory {item}")
                continue
            
            comments_file = os.path.join(item, "comments.json")
            if os.path.exists(comments_file):
                patch_comments(comments_file)

if __name__ == "__main__":
    main()
