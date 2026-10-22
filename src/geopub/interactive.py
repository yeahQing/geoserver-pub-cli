"""交互式选项选择（基于 questionary）。"""

import questionary


def choose_items(items: list[str], message: str = "请选择") -> list[str]:
    """多选勾选，返回被选中的项；用户取消则返回空列表。"""
    if not items:
        return []
    selected = questionary.checkbox(message, choices=items).ask()
    return selected or []
