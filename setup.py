# -*- coding: utf-8 -*-
from pathlib import Path
from setuptools import setup, find_packages
import re

ROOT = Path(__file__).parent.resolve()
README = ROOT / "README.md"
REQS  = ROOT / "requirements.txt"
INIT  = ROOT / "pywebcopy" / "__init__.py"

def read_version():
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', INIT.read_text(encoding="utf-8"), re.M)
    if not m:
        raise RuntimeError("Cannot find __version__ in pywebcopy/__init__.py")
    return m.group(1)

def read_requires():
    if not REQS.exists():
        return []
    return [
        ln.strip() for ln in REQS.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]

setup(
    name="pywebcopy",                      # hardcode package name
    version=read_version(),                # parsed from __init__.py (no import)
    description="High-level website copier / snapshotter",
    long_description=README.read_text(encoding="utf-8") if README.exists() else "",
    long_description_content_type="text/markdown",
    author="(unknown)",
    author_email="",
    url="",
    license="MIT",
    packages=find_packages(include=["pywebcopy", "pywebcopy.*"]),
    include_package_data=True,
    install_requires=read_requires(),
    python_requires=">=3.8",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
