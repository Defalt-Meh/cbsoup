/*
 * data-types.h (a.k.a. shared parser types & macros)
 * Copyright (C) 2017 Kovid Goyal
 * Apache 2.0
 *
 * notes:
 * - This header is included from both C and C++. Keep it *boring* and predictable.
 * - Don’t play macro golf. If a macro can bite you with side-effects, don’t use it.
 * - If you “optimize” these helpers, you’re probably just making bugs faster.
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>   /* because “bool” shouldn’t be a religion */
#include <stddef.h>    /* size_t for sanitize_name() */
#include "../gumbo/gumbo.h"

/* ----------------------------- Attributes & Options -------------------------
 * Options: the knobs you can turn without having to rewrite the parser.
 * If you add a field, initialize it everywhere. Don’t rely on stacked garbage.
 */
typedef struct {
    unsigned int stack_size;          /* iterative DFS stack capacity (bytes-ish) */
    bool keep_doctype;                /* preserve <!DOCTYPE ...> if present */
    bool namespace_elements;          /* attach xmlns and set element ns */
    bool sanitize_names;              /* clamp tag/attr names to a safe subset */
    const void* line_number_attr;     /* interned name for line-number attribute (or NULL) */
    GumboOptions gumbo_opts;          /* pass-through Gumbo configuration */
} Options;

/* Attribute enumeration:
 * This is generated (attr_enum.h). If you change its order, you break lookups.
 * HTML_ATTR_LAST is a sentinel for bounds checks; don’t store it as a real attr.
 */
typedef enum {
#include "attr_enum.h"
  /* Marker value: end of enum for iteration and bounds checks. */
  HTML_ATTR_LAST,
} HTMLAttr;

/* ------------------------------- Export / Hints -----------------------------
 * Shared visibility & branch prediction hints. If your compiler ignores them,
 * fine. The code must still behave.
 */
#ifdef _MSC_VER
  #define UNUSED 
  #define EXPORTED __declspec(dllexport)
#else
  #define UNUSED __attribute__ ((unused))
  #define EXPORTED __attribute__ ((visibility ("default")))
#endif

#ifdef __builtin_expect
  #define LIKELY(x)    __builtin_expect(!!(x), 1)
  #define UNLIKELY(x)  __builtin_expect(!!(x), 0)
#else
  #define LIKELY(x)    (x)
  #define UNLIKELY(x)  (x)
#endif

/* MIN/MAX:
 * These evaluate arguments more than once. Don’t pass expressions with side-effects.
 * If you need safety, write a function. Here we prefer zero overhead.
 */
#define MIN(x, y) ((x) < (y) ? (x) : (y))
#define MAX(x, y) ((x) > (y) ? (x) : (y))

/* Upper bound for scratch buffers used in tag/attr munging. If you think 100
 * is small, show me real HTML that needs more. Otherwise, don’t bike-shed it.
 */
#define MAX_TAG_NAME_SZ 100

/* ----------------------------- Name Sanitization ----------------------------
 * We accept a *subset* of XML NameStartChar/NameChar. Why? Because handling the
 * full spec on raw UTF-8 without decoding is a foot-gun. This subset is:
 *   first:  [A-Za-z_]
 *   rest:   [A-Za-z0-9_.-]
 * If you need more, add tests first. Then maybe we talk.
 */

/* Fast ASCII checks you can run on UTF-8 bytes without decoding. */
#define VALID_FIRST_CHAR(c) ( \
    ((c) >= 'a' && (c) <= 'z') || \
    ((c) >= 'A' && (c) <= 'Z') || \
    (c) == '_' \
)

#define VALID_CHAR(c) ( \
    ((c) >= 'a' && (c) <= 'z') || \
    ((c) >= '0' && (c) <= '9') || \
    ((c) == '-') || \
    ((c) >= 'A' && (c) <= 'Z') || \
    ((c) == '_') || ((c) == '.') \
)

/* Cute preprocessor tricks. Keep them contained. */
#define STRFY(x)  #x
#define STRFY2(x) STRFY(x)

/* Error strings that point at the *actual* line in the compiled unit.
 * If this message fires, it’s your bug. Own it. */
#define ERRMSG(x) ("File: " __FILE__ " Line: " STRFY2(__LINE__) ": " x)
#define NOMEM     (ERRMSG("Out of memory"))

/* sanitize_name:
 * In-place clamp of a tag/attribute name. Replaces illegal bytes with '_'.
 * Returns the new length (aka first '\0' index). Yes, it’s O(n). No, you don’t
 * need SIMD here.
 *
 * Foot-guns:
 * - You pass us a writable, NUL-terminated buffer. If you don’t, don’t be surprised.
 * - We only touch ASCII bytes; multi-byte UTF-8 sequences get clobbered at the
 *   first byte if they don’t pass the cheap test. That’s the design.
 */
#ifdef NEEDS_SANITIZE_NAME
static inline size_t sanitize_name(char *name) {
    if (UNLIKELY(name[0] == 0)) return 0;
    if (UNLIKELY(!VALID_FIRST_CHAR((unsigned char)name[0]))) name[0] = '_';
    size_t i = 1;
    for (; name[i] != 0; i++) {
        if (UNLIKELY(!VALID_CHAR((unsigned char)name[i]))) name[i] = '_';
    }
    return i;
}
#endif

#ifdef __cplusplus
} /* extern "C" */
#endif
