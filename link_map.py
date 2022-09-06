#!/usr/bin/env python3

from collections import OrderedDict
import itertools
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class LinkMapLine:
    vma: str
    lma: str
    size: str
    align: str
    out: str
    in_: str
    symbol: str


def assert_equal(a: List[str], b: List[str]):
    assert a == b, f"Expected {a} to equal {b}"


def parse_space_separated(l) -> List[str]:
    return [a for a in l.split(" ") if a]


def parse_positional(l: str, idx: int) -> str:
    a = l[idx:]
    if a and a[0] != " ":
        a = a.strip()
    else:
        a = ""
    return a


def tokenize_link_map(content: str) -> List[LinkMapLine]:
    lines = content.splitlines()
    while not lines[0]:
        lines = lines[1:]
    heading_line = lines[0]
    heading = parse_space_separated(heading_line)
    assert_equal(heading, ["VMA", "LMA", "Size", "Align", "Out", "In", "Symbol"])
    out_idx = heading_line.find("Out")
    assert out_idx > 0
    in_idx = heading_line.find("In")
    assert in_idx > 0
    symbol_idx = heading_line.find("Symbol")
    assert symbol_idx > 0
    elems = []
    for line in lines[1:]:
        regular = parse_space_separated(line[:out_idx])
        out = parse_positional(line, out_idx)
        in_ = parse_positional(line, in_idx)
        symbol = parse_positional(line, symbol_idx)
        elem = LinkMapLine(
            vma=regular[0],
            lma=regular[1],
            size=regular[2],
            align=regular[3],
            out=out,
            in_=in_,
            symbol=symbol,
        )
        elems.append(elem)
    return elems


@dataclass
class Named:
    name: str


@dataclass
class Sized:
    vma: int
    lma: int
    size: int
    align: int


@dataclass
class Symbol(Named, Sized):
    pass


@dataclass
class SectionIn(Named, Sized):
    children: List[Symbol]


@dataclass
class SectionOut(Named, Sized):
    children: List[SectionIn]


def build_tree(elems: List[LinkMapLine]) -> List[SectionOut]:
    section_out: Optional[SectionOut] = None
    section_in: Optional[SectionIn] = None
    assert len(elems[0].out)
    sections_out: List[SectionOut] = []
    sections_in: List[SectionOut] = []
    symbols: List[Symbol] = []

    for elem in elems:
        if elem.out:
            # New out section
            section_out = SectionOut(
                name=elem.out,
                vma=int(elem.vma, base=16),
                lma=int(elem.lma, base=16),
                size=int(elem.size, base=16),
                align=int(elem.align, base=16),
                children=[],
            )
            sections_out.append(section_out)
            sections_in = section_out.children
            continue
        if elem.in_:
            # New in section
            section_in = SectionIn(
                name=elem.in_,
                vma=int(elem.vma, base=16),
                lma=int(elem.lma, base=16),
                size=int(elem.size, base=16),
                align=int(elem.align, base=16),
                children=[],
            )
            sections_in.append(section_in)
            symbols = section_in.children
            continue
        # Add symbol
        symbols.append(
            Symbol(
                vma=int(elem.vma, base=16),
                lma=int(elem.lma, base=16),
                size=int(elem.size, base=16),
                align=int(elem.align, base=16),
                name=elem.symbol,
            )
        )
    return sections_out


def parse_link_map(content: str) -> List[SectionOut]:
    """
    Parse the content of a space-separated link map file into a tree.

    >>> content = '''
    ...          VMA              LMA     Size Align Out     In      Symbol
    ...          2a8              2a8        8     1 .interp
    ...          2a8              2a8        8     1         <internal>:(.interp)
    ...          2b0              2b0       18     4 .note.gnu.build-id
    ...         15b0             15b0    3be92    16 .rodata
    ...         15b0             15b0      310    16         <internal>:(.rodata)
    ...         18c0             18c0       1c     4         foobar.cc
    ...         18c0             18c0       1c     1                 vtable for FOO
    ...         18c0             18c0       1c     1                 vtable for BAR
    ... '''
    >>> tree = parse_link_map(content)
    >>> len(tree)
    3
    >>> tree[0].name
    '.interp'
    >>> tree[0].size
    8
    >>> tree[0].vma
    680
    >>> tree[0].children
    [SectionIn(vma=680, lma=680, size=8, align=1, name='<internal>:(.interp)', children=[])]
    >>> tree[1]
    SectionOut(vma=688, lma=688, size=24, align=4, name='.note.gnu.build-id', children=[])
    >>> tree[2].children[0]
    SectionIn(vma=5552, lma=5552, size=784, align=22, name='<internal>:(.rodata)', children=[])
    >>> tree[2].children[1].children[0]
    Symbol(vma=6336, lma=6336, size=28, align=1, name='vtable for FOO')
    >>> tree[2].children[1].children[1]
    Symbol(vma=6336, lma=6336, size=28, align=1, name='vtable for BAR')
    """
    elems = tokenize_link_map(content)
    return build_tree(elems)


def merge_function_sections(sections: List[SectionIn]) -> List[SectionIn]:
    """
    Merge IN sections which come from identical source files and only differ
    because the compiler makes every function live in its own section.

    >>> content = '''
    ...          VMA              LMA     Size Align Out     In      Symbol
    ...          100              100        8     1 .text
    ...          100              100        8     1         bar.cc.o:(.text._FOO)
    ...          100              100        8     1                 FOO
    ...          108              108        8     1         bar.cc.o:(.text._BAR)
    ...          108              108        8     1                 BAR
    ... '''
    >>> tree = parse_link_map(content)
    >>> before = tree[0].children
    >>> len(before)
    2
    >>> merged = merge_function_sections(before)
    >>> len(merged)
    1
    >>> merged[0]
    SectionIn(vma=256, lma=256, size=16, align=8, name='bar.cc.o', children=[Symbol(vma=256, lma=256, size=8, align=1, name='FOO'), Symbol(vma=264, lma=264, size=8, align=1, name='BAR')])
    """

    def strip_function_name(name: str):
        idx = name.find(".o:(")
        if idx == -1:
            return name
        return name[: idx + 2]

    merged_sections: Dict[str, SectionIn] = OrderedDict()
    for section in sections:
        name = strip_function_name(section.name)
        if name not in merged_sections:
            merged_sections[name] = SectionIn(
                vma=section.vma,
                lma=section.lma,
                size=0,
                align=0,
                name=name,
                children=[],
            )
        merged_section = merged_sections[name]
        merged_section.vma = min(merged_section.vma, section.vma)
        merged_section.lma = min(merged_section.lma, section.lma)
        merged_section.size += section.size
        merged_section.align = max(merged_section.align, section.size)
        merged_section.children.extend(section.children)

    return list(merged_sections.values())


@dataclass
class DiffSized:
    sizes: List[int]
    delta: int


@dataclass
class DiffSymbol(DiffSized, Named):
    pass


@dataclass
class DiffSectionIn(DiffSized, Named):
    children: List[DiffSymbol]


@dataclass
class DiffSectionOut(DiffSized, Named):
    children: List[DiffSectionIn]


def diff_symbols(a: List[Symbol], b: List[Symbol]) -> List[DiffSymbol]:
    # Make a dictionary of {names: (a, b)}
    # For each item, record the difference, and compare the children
    union: Dict[str, Tuple[Symbol, Symbol]] = OrderedDict()
    names_a: Dict[str, Symbol] = {e.name: e for e in a}
    names_b: Dict[str, Symbol] = {e.name: e for e in b}
    for name in itertools.chain(names_a.keys(), names_b.keys()):
        if name in union:
            continue
        e_a = names_a.get(name)
        if e_a is None:
            e_a = Symbol(vma=0, lma=0, size=0, align=0, name=name)
        e_b = names_b.get(name)
        if e_b is None:
            e_b = Symbol(vma=0, lma=0, size=0, align=0, name=name)
        union[name] = (e_a, e_b)
    diff: List[DiffSymbol] = []
    for name, (e_a, e_b) in union.items():
        if e_a.size == e_b.size:
            continue
        diff.append(
            DiffSymbol(
                sizes=[e_a.size, e_b.size],
                delta=e_b.size - e_a.size,
                name=name,
            )
        )
    return diff


def diff_section_in(a: List[SectionIn], b: List[SectionIn]) -> List[DiffSectionIn]:
    # Make a dictionary of {names: (a, b)}
    # For each item, record the difference, and compare the children
    union: Dict[str, Tuple[SectionIn, SectionIn]] = OrderedDict()
    names_a: Dict[str, SectionIn] = {e.name: e for e in a}
    names_b: Dict[str, SectionIn] = {e.name: e for e in b}
    for name in itertools.chain(names_a.keys(), names_b.keys()):
        if name in union:
            continue
        e_a = names_a.get(name)
        if e_a is None:
            e_a = SectionIn(vma=0, lma=0, size=0, align=0, name=name, children=[])
        e_b = names_b.get(name)
        if e_b is None:
            e_b = SectionIn(vma=0, lma=0, size=0, align=0, name=name, children=[])
        union[name] = (e_a, e_b)
    diff: List[DiffSectionIn] = []
    for name, (e_a, e_b) in union.items():
        if e_a.size == e_b.size:
            continue
        diff.append(
            DiffSectionIn(
                sizes=[e_a.size, e_b.size],
                delta=e_b.size - e_a.size,
                name=name,
                children=diff_symbols(e_a.children, e_b.children),
            )
        )
    return diff


def diff_link_map(a: List[SectionOut], b: List[SectionOut]) -> List[DiffSectionOut]:
    """
    Compare the member sizes between two link maps, and output the differences.
    When comparing across link maps, members are identified by their name.
    Deltas are all computed relative to the first link map.

    >>> content_a = '''
    ...          VMA              LMA     Size Align Out     In      Symbol
    ...          2a8              2a8        8     1 foo
    ...          2a8              2a8        8     1         bar
    ...          2b0              2b0       12     4 baz
    ...          3b0              3b0        a     2 new
    ... '''
    >>> content_b = '''
    ...          VMA              LMA     Size Align Out     In      Symbol
    ...          2a8              2a8       10     1 foo
    ...          2a8              2a8       20     1         bar
    ...          2b0              2b0       40     4 baz
    ... '''
    >>> diff = diff_link_map(parse_link_map(content_a), parse_link_map(content_b))
    >>> diff[0]
    DiffSectionOut(name='foo', sizes=[8, 16], delta=8, children=[DiffSectionIn(name='bar', sizes=[8, 32], delta=24, children=[])])
    >>> diff[1]
    DiffSectionOut(name='baz', sizes=[18, 64], delta=46, children=[])
    >>> diff[2]
    DiffSectionOut(name='new', sizes=[10, 0], delta=-10, children=[])
    """
    # Make a dictionary of {names: (a, b)}
    # For each item, record the difference, and compare the children
    union: Dict[str, Tuple[SectionOut, SectionOut]] = OrderedDict()
    names_a: Dict[str, SectionOut] = {e.name: e for e in a}
    names_b: Dict[str, SectionOut] = {e.name: e for e in b}
    for name in itertools.chain(names_a.keys(), names_b.keys()):
        if name in union:
            continue
        e_a = names_a.get(name)
        if e_a is None:
            e_a = SectionOut(vma=0, lma=0, size=0, align=0, name=name, children=[])
        e_b = names_b.get(name)
        if e_b is None:
            e_b = SectionOut(vma=0, lma=0, size=0, align=0, name=name, children=[])
        union[name] = (e_a, e_b)
    diff: List[DiffSectionOut] = []
    for name, (e_a, e_b) in union.items():
        if e_a.size == e_b.size:
            continue
        diff.append(
            DiffSectionOut(
                sizes=[e_a.size, e_b.size],
                delta=e_b.size - e_a.size,
                name=name,
                children=diff_section_in(e_a.children, e_b.children),
            )
        )
    return diff


if __name__ == "__main__":
    import doctest

    doctest.testmod()
