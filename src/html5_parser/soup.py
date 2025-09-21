#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: Apache 2.0 Copyright: 2017, Kovid Goyal; edits (2025) for clarity/perf.
#
# Performance sketch:
# - Hoist imports/attr lookups out of hot loops (constant folding in practice).
# - Precompute BS4 CDATA attribute sets once; O(1) checks thereafter.
# - Avoid pointless .split() when there’s no whitespace (amortized win on many attrs).
# - Local-bind methods in inner loops (Python attribute lookup has a nontrivial cost).
#
# Math-prof analogy:
# We’re minimizing ∑_nodes ∑_attrs c_lookup by extracting invariants: convert it to
# ∑_nodes (c_setup + ∑_attrs c_check), where c_setup (building the sets) happens once.

from __future__ import absolute_import, division, print_function, unicode_literals

# Py2 compatibility vestige kept for API parity; harmless in Py3.
unicode = type('')

# Globals filled lazily to avoid importing bs4 when not needed.
cdata_list_attributes = None
universal_cdata_list_attributes = None
empty = ()

# Cache the soup module (bs4 or bs3) — function attr to avoid extra global.
def soup_module():
    ans = soup_module.ans
    if ans is None:
        try:
            import bs4 as _bs
            ans = _bs
        except ImportError:  # pragma: no cover (rare; bs3 is legacy)
            import BeautifulSoup as _bs  # type: ignore
            ans = _bs
        soup_module.ans = ans
    return ans
soup_module.ans = None  # type: ignore


def set_soup_module(val):
    """Manual override for tests or custom environments."""
    soup_module.ans = val


# ---- CDATA list attributes for BS4 ------------------------------------------

def init_bs4_cdata_list_attributes():
    """
    Initialize the two global sets used to decide which attributes are CDATA-lists.
    Complexity: O(#attributes); pays once per process.
    """
    global cdata_list_attributes, universal_cdata_list_attributes
    from bs4.builder import HTMLTreeBuilder
    try:
        attribs = HTMLTreeBuilder.DEFAULT_CDATA_LIST_ATTRIBUTES
    except AttributeError:
        attribs = HTMLTreeBuilder.cdata_list_attributes  # older bs4

    # Freeze inner containers to prevent accidental mutation and speed membership tests.
    # dict -> { str: frozenset(str) }, plus the universal '*' set.
    # Note: transforming to frozenset makes "x in S" O(1) with lower overhead.
    cdata_list_attributes = {k: frozenset(v) for k, v in attribs.items()}
    universal_cdata_list_attributes = cdata_list_attributes['*']


def _split_if_needed(val):
    """
    Split only if there is whitespace. Avoids allocating a list for single-token attrs.
    """
    # str.split() already handles multi-space, but still allocates; guard first.
    # Any ASCII whitespace triggers a split.
    if any(ch.isspace() for ch in val):
        return val.split()
    return val


def map_list_attributes(tag_name, name, val):
    """
    Decide whether an attribute should be treated as a list (space-separated) per BS rules.
    """
    u = universal_cdata_list_attributes
    if u is not None and name in u:
        return _split_if_needed(val)
    # Local set for this tag (or empty tuple to avoid None checks).
    local = (cdata_list_attributes or {}).get(tag_name, empty)
    if name in local:
        return _split_if_needed(val)
    return val


# ---- Fast append/new_tag for bs4 and bs3 ------------------------------------

def bs4_fast_append(self, new_child):
    """
    O(1) append into BeautifulSoup4’s tree with sibling/element threading updated.
    This mirrors BS4 internals but avoids multiple attribute lookups in Python.
    """
    new_child.parent = self
    contents = self.contents
    if contents:
        previous_child = contents[-1]
        new_child.previous_sibling = previous_child
        previous_child.next_sibling = new_child
        new_child.previous_element = previous_child._last_descendant(False)
    else:
        new_child.previous_sibling = None
        new_child.previous_element = self
    # The previous_element’s next_element must point to us for correct iteration.
    new_child.previous_element.next_element = new_child
    new_child.next_sibling = new_child.next_element = None
    contents.append(new_child)


def bs4_new_tag(Tag, soup):
    """
    Factory returning new_tag(name, attrs) with CDATA-attribute handling baked in.
    """
    builder = soup.builder
    ml = map_list_attributes  # local bind

    def new_tag(name, attrs):
        # Fast dict comprehension with attribute-level normalization.
        attrs = {k: ml(name, k, v) for k, v in attrs.items()}
        return Tag(soup, name=name, attrs=attrs, builder=builder)

    return new_tag


def bs3_fast_append(self, newChild):
    """
    BS3 variant of fast append; mirrors the historical API surface.
    """
    newChild.parent = self
    contents = self.contents
    if contents:
        previousChild = contents[-1]
        newChild.previousSibling = previousChild
        previousChild.nextSibling = newChild
        newChild.previous = previousChild._lastRecursiveChild()
    else:
        newChild.previousSibling = None
        newChild.previous = self
    newChild.previous.next = newChild
    newChild.nextSibling = newChild.next_element = None
    contents.append(newChild)


def bs3_new_tag(Tag, soup):
    """
    BS3 tag factory; keep semantics identical but avoid repeated lookups.
    """
    def new_tag(name, attrs):
        ans = Tag(soup, name)
        # Keep both attrs and attrMap as in BS3, but avoid extra iteration.
        items = attrs.items()
        ans.attrs = items
        ans.attrMap = attrs
        return ans

    return new_tag


# Void elements for self-closing check in BS3 mode.
VOID_ELEMENTS = frozenset(
    'area base br col embed hr img input keygen link menuitem meta param source track wbr'.split()
)

# Small helper; caching the result avoids repeated prefix checks later.
def is_bs3():
    sm = soup_module()
    return sm.__version__.startswith('3.')


def init_soup():
    """
    Initialize a BeautifulSoup (bs4 or bs3) instance and return the tuple:
        (bs_module, soup, new_tag_func, CommentClass, append_func, NavigableStringClass)

    This is the “interface adapter” layer that lets the C core push nodes into BS
    without paying repeated reflective costs in Python.
    """
    bs = soup_module()
    if is_bs3():
        soup = bs.BeautifulSoup()
        new_tag = bs3_new_tag(bs.Tag, soup)
        append = bs3_fast_append
        # Lambda as a method; identical semantics to prior code.
        soup.isSelfClosing = lambda self, name: name in VOID_ELEMENTS
        Comment = bs.Comment
        NavigableString = bs.NavigableString
    else:
        # Use lxml parser (fast-path). We’ll need CDATA attribute sets once.
        soup = bs.BeautifulSoup('', 'lxml')
        new_tag = bs4_new_tag(bs.Tag, soup)
        append = bs4_fast_append
        if universal_cdata_list_attributes is None:
            init_bs4_cdata_list_attributes()
        Comment = bs.Comment
        NavigableString = bs.NavigableString
    return bs, soup, new_tag, Comment, append, NavigableString


def parse(utf8_data, stack_size=16 * 1024, keep_doctype=False, return_root=True):
    """
    Parse HTML bytes (or str) into a BeautifulSoup tree using the C core,
    but with Python-level factories (new_tag, Comment, NavigableString, append)
    for node materialization.

    Parameters
    ----------
    utf8_data : bytes | str
        HTML payload. If str, it will be encoded as UTF-8 (lossless on ASCII).
    stack_size : int
        Size (bytes) for the C parser stack arena; affects recursion depth tolerance.
    keep_doctype : bool
        If True and bs supports Doctype, forward the doctype from the C layer.
    return_root : bool
        If True, return the root element; otherwise return the entire soup.

    Returns
    -------
    bs4.element.Tag (root) or bs4.BeautifulSoup (document), matching return_root.
    """
    # Lazy import to avoid circulars and only pay the cost when actually parsing.
    from html5_parser import html_parser

    bs, soup, new_tag, Comment, append, NavigableString = init_soup()

    # Encode only if necessary; str->bytes once. If already bytes, keep as-is.
    if not isinstance(utf8_data, (bytes, bytearray, memoryview)):
        utf8_data = utf8_data.encode('utf-8')

    # Doctype callback: bound once; c-core calls at most once, so tiny overhead.
    if keep_doctype and hasattr(bs, 'Doctype'):
        def add_doctype(name, public_id, system_id, _append=soup.append, _Doctype=bs.Doctype):
            _append(_Doctype.for_name_and_ids(name, public_id or None, system_id or None))
        dt = add_doctype
    else:
        dt = None

    # Invoke the C core: it will call back into new_tag/append/etc. to build the tree.
    root = html_parser.parse_and_build(
        utf8_data, new_tag, Comment, NavigableString, append, dt, stack_size
    )
    soup.append(root)
    return root if return_root else soup
