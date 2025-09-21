/*
 * as-python-tree.h
 * Copyright (C) 2017 Kovid Goyal
 * License: GPLv3
 *
 * notes:
 * - This is a *thin* bridge: Gumbo (C) → Python objects (BeautifulSoup-like).
 *   Keep it simple. If you want a framework, write one somewhere else.
 * - Caller must hold the GIL. If you call into this without the GIL, you
 *   deserve the crash you get.
 * - Ownership rules are explicit below. Don’t guess. Don’t “fix” refcounts.
 */

#pragma once

/* If you break the include order, you get mystery warnings on some compilers.
 * Keep Python first so PY_SSIZE_T_CLEAN actually does something. */
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "data-types.h"
#include "../gumbo/gumbo.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Build a Python tree from a Gumbo parse output.
 *
 * Parameters (all non-NULL, and you MUST hold the GIL):
 *  - gumbo_output : result of Gumbo parsing (owned by caller; still valid for the call)
 *  - opts         : parser/builder options (stack size, sanitization, etc.)
 *  - new_tag      : callable(name:str, attrs:dict) -> Tag
 *  - new_comment  : callable(text:str) -> Comment
 *  - new_string   : callable(text:str) -> NavigableString
 *  - append       : callable(parent:Tag, child:Node) -> any (ignored)
 *
 * Returns:
 *  - New reference to the root Python node (Tag). Caller owns the ref.
 *  - On error: returns NULL and sets a Python exception. No half-built trees leak.
 *
 * Notes:
 *  - Iterative DFS with an explicit stack (no recursion bombs).
 *  - We don’t import bs4 here; you hand us the factories you want.
 *  - If you “optimize” away refcount symmetry, you’ll chase heisenbugs for weeks.
 */
PyObject* as_python_tree(GumboOutput *gumbo_output,
                         Options *opts,
                         PyObject *new_tag,
                         PyObject *new_comment,
                         PyObject *new_string,
                         PyObject *append);

/* Initialize interned name tables used by the builder.
 *
 * Parameters:
 *  - val      : PyTuple pre-sized for all standard HTML tag names
 *               (index == GumboTag value). This function *fills* it.
 *  - attr_val : PyTuple pre-sized for all known HTML attribute names
 *               (index == HTMLAttr value). This function *fills* it.
 *
 * Returns:
 *  - true on success; false on allocation failure (and sets a Python exception).
 *
 * Ownership:
 *  - This function stores the tuples internally for fast lookup but does NOT
 *    steal ownership of the tuple objects themselves. You keep the owning refs.
 *    (Individual PyUnicode entries are inserted with PyTuple_SET_ITEM and thus
 *     are owned by the tuples, as expected.)
 *
 * Foot-guns:
 *  - If the tuples are the wrong size, you’ll write past the logical end.
 *    We don’t add bounds checks here; fix your caller instead.
 */
bool set_known_tag_names(PyObject *val, PyObject *attr_val);

#ifdef __cplusplus
} /* extern "C" */
#endif
