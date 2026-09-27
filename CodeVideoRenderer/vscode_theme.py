"""VS Code visual style: syntax-highlighting theme + Python keyword-splitting lexer.

Provides syntax-highlighting colors matching VS Code's "Dark+" theme, plus a lexer
that splits Python keywords into ``Keyword.Declaration`` (def/class, blue) and
``Keyword.Reserved`` (if/for/return…, purple) so the rendered output closely
resembles real VS Code.
"""
from __future__ import annotations

from pygments.filter import Filter
from pygments.style import Style
from pygments.token import (
    Token, Keyword, Name, Comment, String, Error, Number, Operator,
    Punctuation, Literal, Generic, Whitespace,
)
from pygments.lexers.python import PythonLexer

__all__ = [
    "VSCodeDarkPlusStyle",
    "VSCodePythonLexer",
    "register_vscode",
    "resolve_language",
    "STYLE_NAME",
    "LEXER_NAME",
]

STYLE_NAME = "vscode-dark-plus"
LEXER_NAME = "python-vscode"

# Python language aliases to map onto the VS Code lexer
PYTHON_LANGUAGES = {"python", "python3", "py", "py3", "python2", "py2"}


def resolve_language(language: str) -> str:
    """Map standard Python language names to the VS Code lexer; return other languages unchanged."""
    return LEXER_NAME if language in PYTHON_LANGUAGES else language


class VSCodeDarkPlusStyle(Style):
    """Pygments style whose colors match VS Code's default Dark+ theme."""

    name = STYLE_NAME
    background_color = "#1E1E1E"
    styles = {
        Token: "#D4D4D4",
        Whitespace: "",
        # Comments
        Comment: "#6A9955",
        Comment.Preproc: "#C586C0",
        # Keywords: def/class/lambda blue; control flow (if/for/return…) purple
        Keyword: "#569CD6",
        Keyword.Constant: "#569CD6",       # None / True / False
        Keyword.Declaration: "#569CD6",    # def / class / lambda
        Keyword.Reserved: "#C586C0",       # if / for / return / import …
        Keyword.Namespace: "#569CD6",
        Keyword.Type: "#4EC9B0",
        # Operators
        Operator: "#D4D4D4",
        Operator.Word: "#C586C0",          # and / or / not / in / is
        # Names
        Name: "#D4D4D4",
        Name.Builtin: "#DCDCAA",           # print / len / range …
        Name.Builtin.Pseudo: "#9CDCFE",    # self / cls
        Name.Function: "#DCDCAA",          # function names
        Name.Function.Magic: "#DCDCAA",    # __init__ etc.
        Name.Class: "#4EC9B0",             # class names
        Name.Namespace: "#4EC9B0",
        Name.Exception: "#4EC9B0",
        Name.Decorator: "#DCDCAA",         # @decorator
        Name.Variable: "#9CDCFE",          # variables
        Name.Constant: "#9CDCFE",
        Name.Attribute: "#9CDCFE",
        Name.Tag: "#569CD6",
        Name.Label: "#9CDCFE",
        # Strings
        String: "#CE9178",
        String.Doc: "#CE9178",
        String.Interpol: "#CE9178",
        String.Escape: "#CE9178",
        String.Regex: "#CE9178",
        String.Symbol: "#CE9178",
        String.Other: "#CE9178",
        # Numbers
        Number: "#B5CEA8",
        # Other
        Punctuation: "#D4D4D4",
        Literal: "#B5CEA8",
        Generic: "#D4D4D4",
        Error: "#F44747",
    }


# Keywords shown purple (control) in VS Code; the rest are blue (def/class)
_CONTROL_KEYWORDS = {
    "if", "elif", "else", "for", "while", "return", "break", "continue",
    "pass", "raise", "try", "except", "finally", "with", "assert",
    "import", "from", "as", "global", "nonlocal", "yield",
    "and", "or", "not", "is", "in", "del", "async", "await",
}


class _VSKeywordFilter(Filter):
    """Split plain ``Keyword`` tokens into Declaration (blue) and Reserved (purple)."""

    def filter(self, lexer, stream):
        for ttype, value in stream:
            if ttype is Keyword:
                if value in _CONTROL_KEYWORDS:
                    yield Keyword.Reserved, value
                else:
                    yield Keyword.Declaration, value
            else:
                yield ttype, value


class VSCodePythonLexer(PythonLexer):
    """Python lexer that additionally separates def/class (blue) from control-flow keywords (purple)."""

    name = "Python (VS Code)"
    aliases = [LEXER_NAME]
    filenames = ["*.py"]

    def __init__(self, **options):
        super().__init__(**options)
        self.add_filter(_VSKeywordFilter())


_registered = False


def register_vscode():
    """Register the custom style and lexer with Pygments (idempotent; silently degrades on failure)."""
    global _registered
    if _registered:
        return
    try:
        from pygments.styles import _STYLE_NAME_TO_MODULE_MAP
        _STYLE_NAME_TO_MODULE_MAP[STYLE_NAME] = (
            "CodeVideoRenderer.vscode_theme",
            "VSCodeDarkPlusStyle",
        )

        from pygments.lexers import LEXERS, _lexer_cache
        LEXERS["VSCodePythonLexer"] = (
            "CodeVideoRenderer.vscode_theme",
            VSCodePythonLexer.name,
            VSCodePythonLexer.aliases,
            VSCodePythonLexer.filenames,
            ("text/x-python",),
        )
        _lexer_cache[VSCodePythonLexer.name] = VSCodePythonLexer
        _registered = True
    except Exception:
        # Registration failure does not affect the library; it just falls back to Pygments' built-in python lexer
        _registered = False


register_vscode()
