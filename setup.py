from __future__ import annotations

import os
from pathlib import Path


def build_extensions():
    if os.getenv("CONFIG_CORE_CYTHONIZE") != "1":
        return []

    try:
        import importlib
        setuptools_module = importlib.import_module("setuptools")
        Extension = getattr(setuptools_module, "Extension")
    except (ImportError, AttributeError) as exc:
        raise RuntimeError("setuptools is required for protected builds") from exc

    try:
        cython_build = importlib.import_module("Cython.Build")
        cythonize = getattr(cython_build, "cythonize")
    except (ImportError, AttributeError) as exc:
        raise RuntimeError("Cython is required for protected builds") from exc

    sources = [
        "loader.py",
        "resolver.py",
        "backend.py",
        "__init__.py",
    ]

    extensions = [
        Extension("config_core." + Path(src).stem, [src])
        for src in sources
    ]
    return cythonize(
        extensions,
        compiler_directives={"language_level": "3"},
        annotate=False,
    )


def main() -> None:
    import importlib

    setup = getattr(importlib.import_module("setuptools"), "setup")
    setup(ext_modules=build_extensions())


if __name__ == "__main__":
    main()
