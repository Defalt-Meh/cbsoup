/*
 * as-libxml.h
 * Copyright (C) 2017 Kovid Goyal
 * Apache 2.0
 *
 *  notes:
 * - This is a *thin* façade over libxml2. Keep it that way.
 * - The whole point of the opaque handle is ABI sanity. Do not leak libxml
 *   internals into this header unless you enjoy rebuild hell.
 * - Ownership rules are explicit below. If you guess, you leak.
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

#include "data-types.h"   /* GumboOutput, Options, ERRMSG, etc. */

/* Opaque document handle.
 * Yeah, it's typedef'd to void on purpose. Users shouldn't know (or care)
 * that it's actually an xmlDocPtr under the hood. Do not “improve” this. */
typedef void libxml_doc;

/* Deep-copy the given document.
 * Returns: a new handle you must free with free_libxml_doc().
 * Params:  doc != NULL
 * Failure: returns NULL (e.g. OOM). */
libxml_doc* copy_libxml_doc(libxml_doc* doc);

/* Destroy a document.
 * Yes, the return type is 'libxml_doc' a.k.a. 'void'. No, that isn’t a typo.
 * Params: doc may be NULL (we tolerate it; freeing NULL is a no-op). */
libxml_doc free_libxml_doc(libxml_doc* doc);

/* libxml2 version as an integer parsed from xmlParserVersion.
 * This is *not* a semantic version. It’s whatever libxml ships, so use it
 * for diagnostics, not feature detection. */
int get_libxml_version(void);

/* Convert a Gumbo tree to a libxml2 document.
 * Ownership: on success you own the returned handle and must free it.
 * On error: returns NULL and, if errmsg is non-NULL, sets *errmsg to a
 * static string describing the error (do NOT free it).
 *
 * Notes:
 * - Options controls namespacing, sanitization, line-number attributes, etc.
 * - We build iteratively with a manual stack; no recursion surprises.
 * - If you want pretty-printing, do it on the caller side; this only builds trees.
 */
libxml_doc* convert_gumbo_tree_to_libxml_tree(GumboOutput *output,
                                              Options *opts,
                                              char **errmsg);

#ifdef __cplusplus
} /* extern "C" */
#endif
