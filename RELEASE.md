# config_core Release & Tagging

This library is versioned **only when the library itself changes**.

## Version fields

- `libs/config_core/__init__.py` â†’ `__version__`
- `libs/config_core/VERSION` â†’ single source of truth
- `libs/config_core/CHANGELOG.md` â†’ human-readable release notes

## When to bump version

Bump the version **only if files under `libs/config_core/` change**.
Other commits in the monorepo do not require a config_core version bump.

## Release steps

1) Update version
- Update `__version__` and `VERSION`
- Add a new section to `CHANGELOG.md`

Optional helper script:

```bash
python scripts/bump_config_core_version.py patch
```

2) Commit
- Commit only the library changes and version files

3) Tag (git)
```
git tag vX.Y.Z
git push origin vX.Y.Z
```

4) Build (optional)
```
python -m pip install --upgrade build
python -m build
```

Protected build (Cython .pyd):
```
set CONFIG_CORE_CYTHONIZE=1
python -m build
```

Build both wheels (pure + protected) with helper script:
```
python scripts/build_configflow.py
```
