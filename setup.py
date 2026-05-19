from __future__ import annotations

import os
from pathlib import Path

from setuptools import Extension, setup


PACKAGE_NAME = "configflow"


def build_extensions():
    """
    Build Cython extensions only when CONFIGFLOW_CYTHONIZE=1.

    This project uses a flat package layout:
    package-dir = {"configflow" = "."}

    So source files are at repository root:
    loader.py, backend.py, config_api.py, etc.
    """

    if os.getenv("CONFIGFLOW_CYTHONIZE") != "1":
        return []

    try:
        from Cython.Build import cythonize
    except ImportError as exc:
        raise RuntimeError("Cython is required for protected builds") from exc

    sources = [
        "backend.py",
        "backends.py",
        "config_api.py",
        "crud_api.py",
        "loader.py",
    ]

    extensions = []

    for src in sources:
        source_path = Path(src)

        if not source_path.exists():
            raise FileNotFoundError(f"Cython source file not found: {source_path}")

        module_name = f"{PACKAGE_NAME}.{Path(src).stem}"

        extensions.append(
            Extension(
                module_name,
                [str(source_path)],
            )
        )

    return cythonize(
        extensions,
        compiler_directives={"language_level": "3"},
        annotate=False,
    )


setup(
    ext_modules=build_extensions(),
)
