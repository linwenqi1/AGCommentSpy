
# 标准库
import re
import json
import logging
import time

# 第三方库
from lxml import etree

# 项目内库
from hmdriver2 import logger
from hmdriver2.driver import Driver
from hmdriver2.proto import Bounds
from hmdriver2.utils import parse_bounds
from xml_utils import XMLElement
from hmdriver2.exception import DeviceNotFoundError
from layout_output import save_layout_temp, save_layout_xml
from xml_utils import json2xml

# APP_TITLE = '//root[1]/Stack[1]/__Common__[1]/Navigation[1]/NavigationContent[1]/NavDestination[1]/NavDestinationContent[1]/Column[1]/Stack[1]/CustomFrameNode[1]/Column[1]/List[1]/ListItem[1]/GridRow[1]/GridCol[1]/Column[1]/RelativeContainer[1]/Column[1]/Text[1]'
# APP_TITLE = '//root[1]/Stack[1]/Stack[1]/Navigation[1]/NavigationContent[1]/NavDestination[1]'
# APP_TITLE = '//*[@text="同程旅行"]'
APP_TITLE = '//*[@id="descript_sub_box"]//Text[1]'
APP_SUBTITLE = '//*[@id="descript_sub_box"]/Button/Stack/Text'
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

def get_text(xml_element: XMLElement):
    return xml_element.attributes.get("text")


logging.getLogger("hmdriver2").setLevel(logging.WARNING)


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
	d = Driver("6CS9K25C03021298")
	d.start_app("com.huawei.hmsapp.appgallery", "MainAbility")

	# Open specific AppGallery app page via aa start and print the layout
	layout = open_section_and_get_layout(
		d,
		"com.huawei.hmsapp.appgallery",
		"MainAbility",
		"https://appgallery.huawei.com/app/detail?id=com.taobao.idlefish4ohos",
		wait=6,
	)


	temp_path = save_layout_xml(layout)
	print(f"Layout XML saved to: {temp_path}")

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
except DeviceNotFoundError as e:
	print(f"Device not found: {e}")
