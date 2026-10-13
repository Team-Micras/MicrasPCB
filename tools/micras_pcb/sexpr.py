"""Span-preserving KiCad S-expression reader.

Every node keeps the byte span it came from, so tools can replace or delete single nodes and
leave the rest of a KiCad file byte-identical (small, reviewable diffs).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+')


@dataclass
class Node:
    start: int
    end: int = -1
    items: list = field(default_factory=list)  # str atoms (quotes stripped) and child Nodes

    @property
    def head(self) -> str | None:
        return self.items[0] if self.items and isinstance(self.items[0], str) else None

    def children(self, head: str | None = None) -> list[Node]:
        return [n for n in self.items if isinstance(n, Node) and (head is None or n.head == head)]

    def child(self, head: str) -> Node | None:
        found = self.children(head)
        return found[0] if found else None

    def atoms(self) -> list[str]:
        return [a for a in self.items[1:] if isinstance(a, str)]

    def prop(self, name: str) -> str | None:
        """Value of a (property "name" "value") child."""
        for p in self.children("property"):
            a = p.atoms()
            if a and a[0] == name:
                return a[1] if len(a) > 1 else ""
        return None


def parse(text: str) -> Node:
    stack: list[Node] = []
    root = None
    for m in _TOKEN.finditer(text):
        tok = m.group()
        if tok == "(":
            stack.append(Node(m.start()))
        elif tok == ")":
            node = stack.pop()
            node.end = m.end()
            if stack:
                stack[-1].items.append(node)
            else:
                root = node
        elif stack:
            stack[-1].items.append(_unquote(tok) if tok.startswith('"') else tok)
    if root is None or stack:
        raise ValueError("unbalanced S-expression")
    return root


def _unquote(tok: str) -> str:
    return re.sub(r"\\(.)", r"\1", tok[1:-1])


def quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fmt(x: float) -> str:
    """KiCad-style number: no trailing zeros, at most 6 decimals."""
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def splice(text: str, edits: list[tuple[int, int, str]]) -> str:
    """Apply (start, end, replacement) edits; spans must not overlap."""
    out, pos = [], 0
    for start, end, rep in sorted(edits):
        if start < pos:
            raise ValueError("overlapping edits")
        out += [text[pos:start], rep]
        pos = end
    out.append(text[pos:])
    return "".join(out)


def line_span(text: str, node: Node) -> tuple[int, int]:
    """The node's span widened to its whole lines, so deleting it leaves no blank line."""
    start = text.rfind("\n", 0, node.start) + 1
    end = text.find("\n", node.end)
    return start, (len(text) if end < 0 else end + 1)
