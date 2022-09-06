#!/usr/bin/env python3

import argparse
import pprint
from pathlib import Path
from link_map import parse_link_map


def main():
    parser = argparse.ArgumentParser("Link map viewer")
    parser.add_argument("path", type=str, help="Path to link map")
    args = parser.parse_args()
    tree = parse_link_map(Path(args.path).read_text())
    for t in tree:
        pprint.pprint(t)


if __name__ == "__main__":
    main()
