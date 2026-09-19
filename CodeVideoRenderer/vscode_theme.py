"""VS Code 视觉风格：语法高亮主题 + Python 关键词拆分词法器。

提供与 VS Code "Dark+" 主题一致的语法高亮配色，以及一个把 Python 关键词
拆分成 ``Keyword.Declaration``（def/class，蓝色）与 ``Keyword.Reserved``
（if/for/return…，紫色）的词法器，使渲染结果尽量贴近真实的 VS Code。
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

# 需要翻译成 VS Code 词法器的 Python 语言别名
PYTHON_LANGUAGES = {"python", "python3", "py", "py3", "python2", "py2"}


def resolve_language(language: str) -> str:
    """把标准 Python 语言名翻译成 VS Code 词法器名，其它语言原样返回。"""
    return LEXER_NAME if language in PYTHON_LANGUAGES else language


class VSCodeDarkPlusStyle(Style):
    """Pygments 风格，配色与 VS Code 默认 Dark+ 主题一致。"""

    name = STYLE_NAME
    background_color = "#1E1E1E"
    styles = {
        Token: "#D4D4D4",
        Whitespace: "",
        # 注释
        Comment: "#6A9955",
        Comment.Preproc: "#C586C0",
        # 关键词：def/class/lambda 蓝，控制流（if/for/return…）紫
        Keyword: "#569CD6",
        Keyword.Constant: "#569CD6",       # None / True / False
        Keyword.Declaration: "#569CD6",    # def / class / lambda
        Keyword.Reserved: "#C586C0",       # if / for / return / import …
        Keyword.Namespace: "#569CD6",
        Keyword.Type: "#4EC9B0",
        # 操作符
        Operator: "#D4D4D4",
        Operator.Word: "#C586C0",          # and / or / not / in / is
        # 名称
        Name: "#D4D4D4",
        Name.Builtin: "#DCDCAA",           # print / len / range …
        Name.Builtin.Pseudo: "#9CDCFE",    # self / cls
        Name.Function: "#DCDCAA",          # 函数名
        Name.Function.Magic: "#DCDCAA",    # __init__ 等
        Name.Class: "#4EC9B0",             # 类名
        Name.Namespace: "#4EC9B0",
        Name.Exception: "#4EC9B0",
        Name.Decorator: "#DCDCAA",         # @decorator
        Name.Variable: "#9CDCFE",          # 变量
        Name.Constant: "#9CDCFE",
        Name.Attribute: "#9CDCFE",
        Name.Tag: "#569CD6",
        Name.Label: "#9CDCFE",
        # 字符串
        String: "#CE9178",
        String.Doc: "#CE9178",
        String.Interpol: "#CE9178",
        String.Escape: "#CE9178",
        String.Regex: "#CE9178",
        String.Symbol: "#CE9178",
        String.Other: "#CE9178",
        # 数字
        Number: "#B5CEA8",
        # 其它
        Punctuation: "#D4D4D4",
        Literal: "#B5CEA8",
        Generic: "#D4D4D4",
        Error: "#F44747",
    }


# VS Code 中呈现为紫色（control）的关键词；其余普通关键词为蓝色（def/class）
_CONTROL_KEYWORDS = {
    "if", "elif", "else", "for", "while", "return", "break", "continue",
    "pass", "raise", "try", "except", "finally", "with", "assert",
    "import", "from", "as", "global", "nonlocal", "yield",
    "and", "or", "not", "is", "in", "del", "async", "await",
}


class _VSKeywordFilter(Filter):
    """把纯 ``Keyword`` token 拆成 Declaration（蓝）与 Reserved（紫）。"""

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
    """Python 词法器：额外区分 def/class（蓝）与控制流关键词（紫）。"""

    name = "Python (VS Code)"
    aliases = [LEXER_NAME]
    filenames = ["*.py"]

    def __init__(self, **options):
        super().__init__(**options)
        self.add_filter(_VSKeywordFilter())


_registered = False


def register_vscode():
    """把自定义风格与词法器注册进 Pygments（幂等，失败时静默降级）。"""
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
        # 注册失败不影响库本身，只是退回到 Pygments 自带的 python 词法器
        _registered = False


register_vscode()
