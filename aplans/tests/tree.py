from __future__ import annotations

from typing import List

class Tree:
    def __init__(self, name: str, indent: int):
        self.name = name
        self.indent = indent
        self.children: List[Tree] = []
        self.parent: Tree | None = None

    @property
    def left_sibling(self):
        if not self.parent:
            return None
        prev_node = None
        for sibling in self.parent.children:
            if sibling == self:
                return prev_node
            prev_node = sibling
        assert False

    def add_child(self, child: Tree):
        self.children.append(child)
        assert child.parent is None
        assert child.indent > self.indent
        child.parent = self

    def equals(self, other: Tree):
        """Determine equality of structure and names, ignoring indentation."""
        return (self.name == other.name
                and len(self.children) == len(other.children)
                and all(x.equals(y) for (x, y) in zip(self.children, other.children)))

    def reset_indent(self, indent=0, shiftwidth=4):
        """Make indentation nice."""
        self.indent = indent
        for child in self.children:
            child.reset_indent(self.indent + shiftwidth, shiftwidth)

    def traverse(self):
        yield self
        for child in self.children:
            yield from child.traverse()

    def get_node(self, name: str) -> Tree | None:
        # This could be optimized
        if self.name == name:
            return self
        for child in self.children:
            node = child.get_node(name)
            if node:
                return node
        return None

    def __repr__(self):
        return self.name

    def __str__(self):
        result = f'{self.indent * " "}{self.name}\n'
        for child in self.children:
            result += str(child)
        return result


def parse_tree_string(tree_string: str, reset_indent=True):
    assert '\t' not in tree_string
    lines = [line.rstrip() for line in tree_string.split('\n') if line.strip()]
    # Dummy root
    root = Tree('<root>', -1)
    stack = [root]
    for i, line in enumerate(lines):
        name = line.lstrip()
        indent = len(line) - len(name)
        last_popped = None
        while indent <= stack[-1].indent:
            last_popped = stack.pop()
        if last_popped and indent < last_popped.indent:
            raise ValueError(f"Invalid indentation for '{name}' at line {i}")
        child = Tree(name, indent)
        stack[-1].add_child(child)
        stack.append(child)
    if reset_indent:
        root.reset_indent(-4, 4)
    # Forget about dummy root
    for child in root.children:
        child.parent = None
    return root.children
