
# 标准库
import re
import json
import logging
import time

# 第三方库
from lxml import etree

# 项目内库
from config import *
from hmdriver2 import logger
from hmdriver2.driver import Driver
from hmdriver2.proto import Bounds
from hmdriver2.utils import parse_bounds
from xml_utils import XMLElement
from hmdriver2.exception import DeviceNotFoundError
from layout_output import save_layout_temp, save_layout_xml
from xml_utils import json2xml
from pathlib import Path
from comments import parse_comment, scrape_comments, save_comments

# ========== 目标应用配置 ==========
PACKAGE_NAME = "com.amap.hmapp"
APP_URL = f"https://appgallery.huawei.com/app/detail?id={PACKAGE_NAME}"
ABILITY = "MainAbility"
MAX_SWIPES = 100
OUTPUT_DIR = Path(PACKAGE_NAME)

def find_components(hierarchy: dict, xpath: str, driver: Driver):
    xml = json2xml(hierarchy)
    result = xml.xpath(xpath)
    results = []

    for node in result:
        raw_bounds: str = node.attrib.get("bounds")  # [832,1282][1125,1412]
        bounds: Bounds = parse_bounds(raw_bounds)
        logger.debug(f"{xpath} Bounds: {bounds}")
        types = re.findall(r'//?(\w+)\[\d+]', xpath)
        results.append(XMLElement(bounds, types[-1] if types else "", node.attrib, driver))

    return results

def find_component(hierarchy: dict, xpath: str, driver: Driver):
	xml = json2xml(hierarchy)
	result = xml.xpath(xpath)

	if len(result) > 0:
		node = result[0]
		raw_bounds: str = node.attrib.get("bounds")  # [832,1282][1125,1412]
		bounds: Bounds = parse_bounds(raw_bounds)
		logger.debug(f"{xpath} Bounds: {bounds}")
		types = re.findall(r'//?(\w+)\[\d+]', xpath)
		return XMLElement(bounds, types[-1] if types else "", node.attrib, driver)

	logger.error(f"xpath: {xpath} not found")
	return None

def scroll_until_component(driver: Driver, xpath: str, max_swipes: int = 10, wait: float = 1.0) -> XMLElement | None:
    """
    Keeps scrolling down until the target component center is within 25%-75% of screen height.
    - Initial state does not count as a swipe
    - Each swipe moves half a screen height (0.8 -> 0.3)
    """
    visible_min_y = SCREEN_HEIGHT * 0.2
    visible_max_y = SCREEN_HEIGHT * 0.8

    def is_visible(component) -> bool:
        if component is None:
            return False
        cy = component.center.y
        return visible_min_y <= cy <= visible_max_y

    # Check initial state (does not count as a swipe)
    layout = driver.dump_hierarchy()
    component = find_component(layout, xpath, driver)
    if is_visible(component):
        print(f"Component found in initial state at y={component.center.y}")
        return component

    for i in range(max_swipes):
        print(f"Swipe {i+1}/{max_swipes} — scrolling half screen...")
        driver.swipe(
            SCREEN_WIDTH // 2, SCREEN_HEIGHT * 0.8,
            SCREEN_WIDTH // 2, SCREEN_HEIGHT * 0.3,
            speed=800
        )
        time.sleep(wait)

        layout = driver.dump_hierarchy()
        component = find_component(layout, xpath, driver)
        if is_visible(component):
            print(f"Component fully visible after {i+1} swipe(s) at y={component.center.y}")
            return component
        elif component is not None:
            print(f"Component found at y={component.center.y} but obscured, scrolling more...")

    print(f"Component not found after {max_swipes} swipes: {xpath}")
    return None

def get_text(xml_element: XMLElement):
    return xml_element.attributes.get("text")


logging.getLogger("hmdriver2").setLevel(logging.WARNING)

def save_app_info(info: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "app_info.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(f"App info saved to: {path.resolve()}")

def get_layout(driver: Driver) -> dict:
	"""Return the UI hierarchy dumped from the given Driver."""
	hierarchy = driver.dump_hierarchy()
	return hierarchy


def open_section_and_get_layout(driver: Driver, package: str, ability: str, url: str, wait: float = 1.0) -> dict:
	"""Open a specific ability with a URL via `aa start` then return the UI layout.

	Args:
		driver: Driver instance.
		package: target package name (e.g. com.huawei.hmsapp.appgallery).
		ability: ability name (e.g. MainAbility).
		url: url to pass with -U.
		wait: seconds to wait for UI to settle before dumping hierarchy.
	"""
	cmd = f'aa start -b {package} -a {ability} -U "{url}"'
	driver.shell(cmd)
	time.sleep(wait)
	return driver.dump_hierarchy()

try:
	d = Driver(DEVICE_ID)
	d.start_app("com.huawei.hmsapp.appgallery", "MainAbility")
	# w, h = d.display_size
	# print(f"Display size: {w}x{h}")
	# Open specific AppGallery app page via aa start and print the layout
	layout = open_section_and_get_layout(
    	d,
    	"com.huawei.hmsapp.appgallery",
    	ABILITY,          # 用 ABILITY 替换 "MainAbility"
    	APP_URL,          # 用 APP_URL 替换硬编码的 url
    	wait=4,
	)


	# temp_path = save_layout_xml(layout)
	# print(f"Layout XML saved to: {temp_path}")

	# 示例：使用 APP_TITLE 查找首页标题并打印其文本
	xe = find_component(layout, APP_TITLE, d)
	if xe and xe.exists():
		print(f"App title text: {xe.text}")
	else:
		print("App title not found")
	sub = find_component(layout, APP_SUBTITLE, d)
	if sub and sub.exists():
		print(f"App subtitle text: {sub.text}")
	else:
		print("App subtitle not found")

	OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
	
	title    = xe.text if xe and xe.exists() else ""
	subtitle = sub.text if sub and sub.exists() else ""
	save_app_info({"title": title, "subtitle": subtitle}, OUTPUT_DIR)

	component = scroll_until_component(d, VIEW_ALL_COMMENTS, max_swipes=10)
    
	if component:
		d.xpath(VIEW_ALL_COMMENTS).click()
		time.sleep(2)
		d.xpath(SORT_BY_LATEST).click()
		time.sleep(2)

    	# test single dump
		layout = d.dump_hierarchy()
		xml = json2xml(layout)
		nodes = xml.xpath(COMMENT_ITEMS)	
		print(f"Found {len(nodes)} comment nodes")

		comments = scrape_comments(d, max_swipes=MAX_SWIPES, wait=1.5)
		save_comments(comments, str(OUTPUT_DIR / "comments.json"))
	else:
		print("'查看全部' button not found")
	print("\nAll tasks completed. Press Ctrl+C to exit.")
	while True:
		time.sleep(1)
except KeyboardInterrupt:
    print("\nStopped by user (Ctrl+C)")
except DeviceNotFoundError as e:
	print(f"Device not found: {e}")
finally:
    try:
        d._client.release()
        print("HDC connection released.")
    except Exception:
        pass
