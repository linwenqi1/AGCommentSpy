import os
import json
import uuid
from typing import Dict, Optional
from lxml import etree
from xml_utils import json2xml

def save_layout_xml(layout: Dict, filename: Optional[str] = None) -> str:
    """
    Save the layout dict as XML under the project's `temp/` directory and return its path.
    """
    project_dir = os.path.dirname(os.path.abspath(__file__))
    temp_dir = os.path.join(project_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    if filename:
        if os.path.isabs(filename):
            path = filename
            os.makedirs(os.path.dirname(path), exist_ok=True)
        else:
            path = os.path.join(temp_dir, filename)
    else:
        name = f"layout_{uuid.uuid4().hex}.xml"
        path = os.path.join(temp_dir, name)

    # Convert dict to XML (reuse json2xml from main.py or require passing xml root)
    
    xml_root = json2xml(layout)
    tree = etree.ElementTree(xml_root)
    tree.write(path, encoding="utf-8", pretty_print=True, xml_declaration=True)
    return path


def save_layout_temp(layout: Dict, filename: Optional[str] = None) -> str:
    """
    Save the layout dict to a JSON file under the project's `temp/` directory and return its path.

    If `filename` is an absolute path it will be used directly. If `filename` is a relative name,
    it will be created inside the project's `temp/` directory. If `filename` is None, a
    filename of the form `layout_<hex>.json` will be created inside `temp/`.
    """
    project_dir = os.path.dirname(os.path.abspath(__file__))
    temp_dir = os.path.join(project_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    if filename:
        if os.path.isabs(filename):
            path = filename
            os.makedirs(os.path.dirname(path), exist_ok=True)
        else:
            path = os.path.join(temp_dir, filename)
    else:
        name = f"layout_{uuid.uuid4().hex}.json"
        path = os.path.join(temp_dir, name)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(layout, f, ensure_ascii=False, indent=2)
    return path
