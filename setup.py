# setup.py (repo root)
from setuptools import setup, Extension
from pathlib import Path
import os

ROOT = Path(__file__).parent.resolve()
SRC = ROOT / "src"
GUMBO_DIR = SRC / "gumbo"

# Detect vendored gumbo sources
VENDORED_FILES = [
    "attribute.c", "char_ref.c", "error.c", "parser.c", "string_piece.c",
    "tag.c", "tokenizer.c", "utf8.c", "util.c", "vector.c",  # some forks add "gumbo.c" too
]
vendored_srcs = [str(GUMBO_DIR / f) for f in VENDORED_FILES if (GUMBO_DIR / f).exists()]
have_vendored = len(vendored_srcs) >= 9  # require most files at least

# Homebrew prefixes (allow env override)
HB_PREFIX = os.environ.get("HOMEBREW_PREFIX")
if not HB_PREFIX:
    if Path("/opt/homebrew").exists():      # Apple Silicon
        HB_PREFIX = "/opt/homebrew"
    else:                                   # Intel mac default
        HB_PREFIX = "/usr/local"

LIBXML2_PREFIX = os.environ.get("LIBXML2_PREFIX", f"{HB_PREFIX}/opt/libxml2")
GUMBO_PREFIX   = os.environ.get("GUMBO_PREFIX",   HB_PREFIX)

include_dirs = [
    str(SRC),                                # your headers (as-*.h, data-types.h)
]
library_dirs = []
libraries    = ["xml2"]

# libxml2 paths
include_dirs.append(f"{LIBXML2_PREFIX}/include/libxml2")
library_dirs.append(f"{LIBXML2_PREFIX}/lib")

# Gumbo: vendored OR system
if have_vendored:
    # compile vendored gumbo into the extension
    gumbo_sources = vendored_srcs
else:
    # link to system gumbo (brew install gumbo-parser)
    gumbo_sources = []
    include_dirs.append(f"{GUMBO_PREFIX}/include")
    library_dirs.append(f"{GUMBO_PREFIX}/lib")
    libraries.append("gumbo")

ext = Extension(
    "html5_parser.html_parser",
    sources=[
        str(SRC / "python-wrapper.c"),
        str(SRC / "as-python-tree.c"),
        str(SRC / "as-libxml.c"),
        *gumbo_sources,
    ],
    include_dirs=include_dirs,
    libraries=libraries,
    library_dirs=library_dirs,
    extra_compile_args=["-O3", "-std=c11", "-Wall", "-Wextra", "-Wno-unused-parameter"],
)

setup(
    name="cbsoup",
    version="0.0.1",
    packages=["html5_parser"],
    package_dir={"": "src"},
    ext_modules=[ext],
)
