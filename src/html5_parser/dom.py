#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: Apache 2.0  (c) 2017 Kovid Goyal; edits (2025) for clarity/perf.
#
# TL;DR performance notes (why this is faster/cleaner):
# - Avoids repeated global lookups inside hot loops by local-binding methods.
# - Precomputes a reverse nsmap per element once (O(k)) instead of scanning
#   the mapping for every attribute (previous code did an O(k) scan per attr).
# - Uses cheap prefix checks (name[0] == '{') rather than startswith('{').
# - Minimizes tiny temporaries and repeated attribute access (e.g., dest_tree).
#
# Mathematical analogy: we’re “factoring the computation” — pulling invariants
# (like per-node namespace context) out of inner sums. If the old code’s cost
# looked like  Σ_nodes Σ_attrs  O(|nsmap|), we cut it to  Σ_nodes ( O(|nsmap|)
# + Σ_attrs O(1) ), which wins when #attrs is nontrivial.

from __future__ import annotations

from xml.dom.minidom import getDOMImplementation
from lxml.etree import _Comment  # lxml's comment node class (private but stable enough)

impl = getDOMImplementation()


def elem_name_parts(elem):
    """
    Given an lxml element, return (uri, qname_for_DOM).
    If elem.tag is '{uri}local' possibly with elem.prefix, reconstitute 'prefix:local'.
    Otherwise (no namespace), return (None, tag).
    """
    tag = elem.tag
    if tag and tag[0] == '{':
        # tag = "{uri}name"
        uri, _, local = tag.rpartition('}')
        uri = uri[1:]  # strip leading '{'
        # When a prefix exists in this context, DOM prefers the 'prefix:local' lexical form.
        if elem.prefix:
            local = elem.prefix + ':' + local
        return uri, local
    return None, tag


def attr_name_parts(name, rev_nsmap, val):
    """
    Attribute name decomposition, using a *reverse* namespace map: {uri -> prefix or None}.
    This makes lookup O(1), instead of scanning elem.nsmap each time.

    If name is '{uri}attr' we resolve to (uri, 'prefix:attr' or 'attr' if no prefix).
    Otherwise we return (None, name, val).
    """
    if name and name[0] == '{':
        uri, _, local = name.rpartition('}')
        uri = uri[1:]
        prefix = rev_nsmap.get(uri)  # O(1)
        if prefix:
            local = prefix + ':' + local
        return uri, local, val
    return None, name, val


def add_namespace_declarations(src, dest):
    """
    Add xmlns declarations on 'dest' that are *new* at 'src' compared to its parent.
    This matches the DOM’s expectation that namespace bindings live on the element
    where they begin to differ (i.e., “local change” principle).

    Complexity: O(#prefixes at src). This is optimal; we only iterate what changed.
    """
    changed = src.nsmap
    if not changed:
        return
    p = src.getparent()
    if p is not None:
        # Only add namespace declarations different from the parent's (if any).
        pmap = p.nsmap or {}
        # Comprehension keeps keys whose URI differs at this depth.
        changed = {k: v for k, v in changed.items() if v != pmap.get(k)}
        if not changed:
            return

    # Local-bind DOM attribute setter for repeated use
    set_attr_ns = dest.setAttributeNS
    for prefix, uri in changed.items():
        # DOM wants the 'xmlns' namespace (uri='xmlns') with qualified attr names.
        # Note: the "namespace URI" for xmlns is the string 'xmlns' in minidom’s API.
        attr_qname = ('xmlns:' + prefix) if prefix else 'xmlns'
        set_attr_ns('xmlns', attr_qname, uri)


def adapt(source_tree, return_root=True, **kw):
    """
    Convert an lxml.etree XML/HTML tree into a stdlib xml.dom.minidom Document
    (or just its root element if return_root=True).

    Think of this as a morphism between two tree categories:
        lxml-tree  →  DOM-tree
    that preserves:
        - node labels (qualified names),
        - namespace structure,
        - textual data (text/tail),
        - comments (with XML-legalization for '--').

    Parameters
    ----------
    source_tree : lxml.etree._ElementTree
    return_root : bool
        If True, return the documentElement; else return the whole Document.

    Returns
    -------
    xml.dom.minidom.Element or xml.dom.minidom.Document
    """
    # Extract source root and create destination DOM with matching qualified root name.
    source_root = source_tree.getroot()
    root_uri, root_qname = elem_name_parts(source_root)

    dest_tree = impl.createDocument(root_uri, root_qname, None)
    # Propagate doctype if present.
    dest_tree.doctype = source_tree.docinfo.doctype

    dest_root = dest_tree.documentElement

    # Local-bind frequently used factories for speed (avoid attribute lookups in loop).
    mk_text = dest_tree.createTextNode
    mk_elem = dest_tree.createElementNS
    mk_comment = dest_tree.createComment

    # Depth-first construction using a stack (iterative to avoid deep recursion).
    # Invariant: each item is (src_node, dest_node) with structure preserved so far.
    stack = [(source_root, dest_root)]
    append = None  # will be rebound per-iteration to dest.appendChild for locality

    while stack:
        src, dest = stack.pop()
        append = dest.appendChild  # local method binding

        # Fast path for text content at the start of the element.
        if src.text:
            append(mk_text(src.text))

        # Namespace deltas at this depth
        add_namespace_declarations(src, dest)

        # Precompute reverse nsmap once per source node: {uri -> prefix or None}
        # This changes only when the source context (element) changes.
        nsmap = src.nsmap or {}
        # Note: nsmap maps prefix->uri; we invert it. If duplicates (rare), last wins—
        # which corresponds to the in-scope binding at this node.
        rev_nsmap = {uri: prefix for prefix, uri in nsmap.items()}

        # Attributes: push in DOM form. Avoid repeated attribute name parsing by
        # calling attr_name_parts with O(1) prefix resolution.
        set_attr_ns = dest.setAttributeNS
        for name, val in src.items():
            set_attr_ns(*attr_name_parts(name, rev_nsmap, val))

        # Children: comments vs elements. For elements, compute qname, push on stack.
        for child in src.iterchildren():
            if isinstance(child, _Comment):
                # XML forbids "--" inside comments; map to em-dash to remain well-formed.
                dchild = mk_comment((child.text or '').replace('--', '—'))
            else:
                cu, cq = elem_name_parts(child)
                dchild = mk_elem(cu, cq)
                # Defer traversal: LIFO stack gives us a depth-first build.
                stack.append((child, dchild))
            append(dchild)

            # Tail text: siblings’ interstitial text belongs to the parent in DOM.
            if child.tail:
                append(mk_text(child.tail))

    return dest_root if return_root else dest_tree
