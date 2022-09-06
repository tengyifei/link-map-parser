#!/usr/bin/env python3

import argparse
import pprint
from pathlib import Path
from link_map import merge_function_sections, parse_link_map, diff_link_map


def main():
    parser = argparse.ArgumentParser("Link map differ")
    parser.add_argument("path_a", type=str, help="Path to first link map")
    parser.add_argument("path_b", type=str, help="Path to second link map")
    args = parser.parse_args()
    tree_a = parse_link_map(Path(args.path_a).read_text())
    tree_b = parse_link_map(Path(args.path_b).read_text())
    for e in tree_a:
        e.children = merge_function_sections(e.children)
    for e in tree_b:
        e.children = merge_function_sections(e.children)
    diff = diff_link_map(tree_a, tree_b)
    pprint.pprint(diff)


if __name__ == "__main__":
    main()
