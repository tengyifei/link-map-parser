from pathlib import Path
from typing import List

from link_map import SectionOut, merge_function_sections, parse_link_map


def get_link_map(p: str) -> List[SectionOut]:
    tree = parse_link_map(Path(p).read_text())
    for e in tree:
        e.children = merge_function_sections(e.children)
    return tree
