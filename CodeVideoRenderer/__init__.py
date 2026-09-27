"""
CodeVideoRenderer – A Python animation library for creating dynamic code demonstration videos.

This package provides tools to transform static code into lively animations that simulate
real programming processes, built on top of the Manim engine.

Quick start
-----------

>>> from CodeVideoRenderer import CameraFollowCursorCV
>>> video = CameraFollowCursorCV(
...     code=('string', 'print("Hello, World!")'),
...     language='python',
...     video_name='HelloWorld'
... )
>>> video.render()

Modules
-------

* :mod:`~.renderer` — Core rendering engine (:class:`~.CameraFollowCursorCV`).
* :mod:`~.postprocess` — Video post-processing helpers (subtitles, audio, quality, watermarks, …).
* :mod:`~.vscode_theme` — VS Code Dark+ syntax-highlighting theme and lexer.
* :mod:`~.ime` — Chinese IME (pinyin + candidates) simulation.
* :mod:`~.config` — Default constants and configuration values.
* :mod:`~.typing` — Type aliases used across the library.
* :mod:`~.utils` — Internal utility functions and helpers.
* :mod:`~.version` — Package version string.
"""
from .renderer import *
from .config import *
from .typing import *
from .utils import *
from .postprocess import *
from .vscode_theme import VSCodeDarkPlusStyle, register_vscode, STYLE_NAME
from .ime import is_cjk, cjk_run_at, get_ime
from .version import __version__