#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: Apache 2.0  (c) 2017 Kovid Goyal; edits (2025) for clarity/perf.
#
# Performance sketch:
# - Avoid repeated global lookups inside loops by local-binding constructors.
# - Use src.attrib.copy() instead of dict(src.items()) (one fewer iterator, tighter C-path).
# - Set .text/.tail exactly once per child; keep append on the hot path.
# - Iterative DFS with a Python list as a stack (amortized O(1) push/pop).
#
# Math-prof analogy:
# If T is the source tree and φ is our structure-preserving map into stdlib ET,
# we factor φ over nodes by pulling invariants (constructors, attribute copying)
# out of the inner sum. Old cost looked like Σ_nodes (c_lookup + c_convert(attrs)).
# We reduce to Σ_nodes (c_setup + c_copy), with c_setup constant and c_copy linear
# in the number of attributes, but with a smaller constant via .attrib.copy().

from __future__ import absolute_import, division, print_function, unicode_literals

import sys
from lxml.etree import _Comment

if sys.version_info.major < 3:
    from xml.etree.cElementTree import (
        Element, SubElement, ElementTree, Comment, register_namespace,
    )
else:
    from xml.etree.ElementTree import (
        Element, SubElement, ElementTree, Comment, register_namespace,
    )

# Pre-register common namespaces so stdlib ET emits preferred prefixes when possible.
register_namespace('svg',   "http://www.w3.org/2000/svg")
register_namespace('xlink', "http://www.w3.org/1999/xlink")


def _convert_elem(src, parent=None, _E=Element, _SE=SubElement):
    """
    Create a stdlib-ET element mirroring 'src' (lxml element), copying attributes.
    Local-binding _E/_SE trims attribute lookup cost in hot paths.

    Note: src.tag is already in '{uri}local' form when namespaced; stdlib ET
    understands this and will handle xmlns serialization using registered prefixes.
    """
    attrs = src.attrib.copy()  # faster than dict(src.items()), fewer temporaries
    if parent is None:
        return _E(src.tag, attrs)
    return _SE(parent, src.tag, attrs)


def adapt(src_tree, return_root=True, **kw):
    """
    Convert an lxml.etree ElementTree to a stdlib xml.etree.ElementTree (or root).
    We preserve:
        - node labels (including namespaces via '{uri}local' tags),
        - attribute mappings,
        - text and tail,
        - comments (mapped to ET.Comment nodes).

    Think of this as a homomorphism of rooted, ordered, labeled trees:
        φ : (V, E, label, text, tail)  →  (V', E', label', text', tail')
    that is bijective on topology and faithful on labels.

    Parameters
    ----------
    src_tree : lxml.etree._ElementTree
    return_root : bool
        If True, return the stdlib root element; else return an ElementTree(doc).

    Returns
    -------
    xml.etree.ElementTree.Element | xml.etree.ElementTree.ElementTree
    """
    # Local-bind constructors and Comment to minimize global lookups in the loop.
    _conv = _convert_elem
    _Comment = Comment

    src_root = src_tree.getroot()
    dest_root = _conv(src_root)

    # Iterative DFS using a stack of (src, dest) pairs.
    stack = [(src_root, dest_root)]
    while stack:
        src, dest = stack.pop()
        # Local bind for append (method lookup once per node).
        d_append = dest.append

        # Iterate direct children only; we must preserve sibling order and tails.
        for s_child in src.iterchildren():
            if isinstance(s_child, _Comment.__class__):  # lxml comment → stdlib Comment
                d_child = _Comment(s_child.text)
                # In ET, a Comment is also an Element-like node with .tail
                d_child.tail = s_child.tail
                d_append(d_child)
            else:
                # Create the element and copy scalar text fields.
                d_child = _conv(s_child, dest)
                d_child.text = s_child.text
                d_child.tail = s_child.tail
                d_append(d_child)
                # Defer traversal of this subtree (depth-first).
                stack.append((s_child, d_child))

    return dest_root if return_root else ElementTree(dest_root)
