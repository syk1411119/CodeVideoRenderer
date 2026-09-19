from __future__ import annotations

# 包版本号。优先读取已安装发行版的版本，未安装（直接运行源码）时回退到此硬编码值。
__version__ = "1.5.0"

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("codevideorenderer")
except Exception:  # pragma: no cover - 仅在未安装发行版时触发
    pass
