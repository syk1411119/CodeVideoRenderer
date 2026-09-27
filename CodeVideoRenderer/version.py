from __future__ import annotations

# Package version. Prefer the installed distribution's version; fall back to this
# hardcoded value when not installed (running from source).
__version__ = "1.5.0"

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("codevideorenderer")
except Exception:  # pragma: no cover - only triggered when the distribution is not installed
    pass
