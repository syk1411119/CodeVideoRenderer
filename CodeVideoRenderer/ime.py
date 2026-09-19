"""中文输入法（IME）候选框模拟：拼音 + 候选词。

渲染代码时遇到汉字，弹出类似输入法的候选框：上面是带横杠分隔的拼音，
下面用一条横线隔开，再列出候选汉字/词语，尽量贴近真实的 IME。
"""
from __future__ import annotations

from typing import List, Tuple

try:
    from pypinyin import pinyin as _py, Style as _Style
    _HAS_PYPINYIN = True
except ImportError:  # pragma: no cover - 未安装 pypinyin 时退化为原字
    _HAS_PYPINYIN = False

__all__ = ["is_cjk", "cjk_run_at", "get_ime"]

# 常见单字/词语的同音候选，让候选框看起来真实（拼音 -> 候选列表）
_CANDIDATES = {
    # 单字
    "ni": ["你", "泥", "拟", "尼", "逆"],
    "hao": ["好", "号", "浩", "耗", "毫"],
    "shi": ["世", "是", "事", "试", "市"],
    "jie": ["界", "借", "接", "街", "解"],
    "da": ["打", "大", "答", "达", "搭"],
    "wan": ["完", "玩", "碗", "晚", "万"],
    "dai": ["代", "带", "待", "戴", "贷"],
    "ma": ["码", "马", "妈", "吗", "麻"],
    "zi": ["自", "字", "资", "紫", "子"],
    "dong": ["动", "东", "懂", "冬", "洞"],
    "qing": ["清", "请", "情", "轻", "青"],
    "ping": ["屏", "平", "评", "苹", "凭"],
    "zhong": ["中", "种", "重", "终", "众"],
    "wen": ["文", "问", "闻", "温", "稳"],
    "yan": ["演", "眼", "盐", "严", "言"],
    "hou": ["后", "候", "厚", "喉", "猴"],
    "hui": ["会", "回", "惠", "汇", "灰"],
    "qi": ["契", "气", "起", "器", "期"],
    "shu": ["数", "书", "树", "输", "术"],
    "fei": ["斐", "飞", "非", "肥", "费"],
    "bo": ["波", "播", "拨", "玻", "伯"],
    "na": ["那", "哪", "拿", "纳", "呐"],
    "di": ["第", "地", "的", "底", "弟"],
    "ge": ["个", "各", "歌", "格", "哥"],
    # 双字词（拼接后的全拼）
    "nihao": ["你好", "你", "泥", "拟", "尼"],
    "shijie": ["世界", "试解", "时间", "四季", "师姐"],
    "daima": ["代码", "大马", "打码", "大妈"],
    "dawan": ["打完", "大碗", "答万"],
    "yanshi": ["演示", "严实", "延时", "验尸"],
    "zhongwen": ["中文", "种闻", "重文"],
    "zidong": ["自动", "字动", "资东"],
    "qingping": ["清屏", "轻评"],
    "houqi": ["后期", "厚起"],
    "chuli": ["处理", "除理", "矗立"],
    "feibo": ["斐波", "飞播"],
    "naqi": ["那契", "纳气"],
    "shuru": ["输入", "书入", "数如"],
    "hanzi": ["汉字", "含字"],
    "wancheng": ["完成", "碗城"],
    "chengxu": ["程序", "成序", "城需"],
}


def is_cjk(ch: str) -> bool:
    """是否为 CJK 汉字。"""
    return len(ch) == 1 and "一" <= ch <= "鿿"


def cjk_run_at(text: str, index: int) -> Tuple[int, int]:
    """返回包含 ``index`` 的连续汉字区间的 ``(start, end)``（end 不含）。"""
    if not (0 <= index < len(text)) or not is_cjk(text[index]):
        return index, index
    start = index
    while start > 0 and is_cjk(text[start - 1]):
        start -= 1
    end = index + 1
    while end < len(text) and is_cjk(text[end]):
        end += 1
    return start, end


def _char_pinyin(ch: str) -> str:
    if not _HAS_PYPINYIN:
        return ch
    try:
        parts = _py(ch, style=_Style.NORMAL, errors=lambda x: [x])
        return (parts[0][0] if parts and parts[0] else ch).lower()
    except Exception:
        return ch


def get_ime(text: str, index: int) -> Tuple[str, List[str]]:
    """返回 ``(拼音, 候选词列表)``。

    拼音取该汉字串前两个字（不足两个则取全部），音节之间用 ``-``（横杠）连接；
    候选词从内置同音表查找，查不到时退化为原字本身。
    """
    start, end = cjk_run_at(text, index)
    if start >= end:
        return "", []
    word = text[start:start + 2]
    pinyin = "-".join(_char_pinyin(c) for c in word)
    key = pinyin.replace("-", "").lower()
    candidates = _CANDIDATES.get(key)
    if not candidates:
        candidates = [word]
    elif word not in candidates:
        candidates = [word] + list(candidates)
    return pinyin, candidates
