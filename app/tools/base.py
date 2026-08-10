"""工具实现公共辅助函数。"""


def norm(text: str | None) -> str:
    """归一化文本用于匹配：去空白、转小写。"""
    return "".join((text or "").split()).lower()


def contains_any(text: str | None, keywords: list[str]) -> bool:
    """判断文本是否包含任一关键词（归一化后子串匹配）。"""
    t = norm(text)
    return any(norm(k) in t for k in keywords)


def first_present(*values):
    """返回第一个非 None 非空值。"""
    for v in values:
        if v:
            return v
    return None
