from lxml import etree

from hmdriver2._xpath import _XMLElement


class XMLElement(_XMLElement):
    """Wrapper around _XMLElement that accepts the 4-arg constructor used by main.py."""

    def __init__(self, bounds, type_str, attrib, driver):
        super().__init__(bounds, driver)
        self.attributes = attrib
        self.attrib_info = attrib
        self.type = type_str


def json2xml(hierarchy: dict) -> etree.Element:
    attributes = hierarchy.get("attributes", {})
    tag = attributes.get("type", "orgRoot") or "orgRoot"
    xml = etree.Element(tag, attrib=attributes)

    children = hierarchy.get("children", [])
    for item in children:
        xml.append(json2xml(item))
    return xml
