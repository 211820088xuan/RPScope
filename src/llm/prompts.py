"""统一 prompt 加载器 — 启动时加载并缓存, 支持变量插值 + 缺失校验。

用法:
    from src.llm.prompts import get_prompt
    msgs = get_prompt("slot_filling", intent="Q1", schema=..., question="...")
    # 返回 [{"role": "system", ...}, {"role": "user", ...}]
"""
from __future__ import annotations

import re
from pathlib import Path

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "prompts"
_CACHE: dict[str, str] = {}  # name -> raw text
_VERSION_MAP: dict[str, str] = {}  # logical name -> versioned filename
_LOADED = False


def _load_all() -> None:
    """启动时一次性加载所有 prompt 文件和版本映射。"""
    global _LOADED
    if _LOADED:
        return

    # 加载版本映射
    import yaml
    versions_path = _PROMPT_DIR / "versions.yaml"
    if not versions_path.exists():
        raise FileNotFoundError(f"prompt 版本配置缺失: {versions_path}")
    with open(versions_path, encoding="utf-8") as f:
        _VERSION_MAP.update(yaml.safe_load(f))

    # 加载每个 prompt 文件
    for logical_name, versioned_name in _VERSION_MAP.items():
        path = _PROMPT_DIR / f"{versioned_name}.txt"
        if not path.exists():
            raise FileNotFoundError(f"prompt 文件缺失: {path}")
        _CACHE[logical_name] = path.read_text(encoding="utf-8")

    _LOADED = True


def _parse(text: str) -> list[tuple[str, str]]:
    """解析 prompt 文本为 (role, content) 列表。

    格式:
      [SYSTEM]\nsys text\n[USER]\nuser text
    或无标记(纯 user):
      user text
    """
    parts = []
    # 检查是否有 [SYSTEM]/[USER] 标记
    sys_match = re.search(r"\[SYSTEM\]\s*\n(.*?)(?=\[USER\]|\Z)", text, re.DOTALL)
    usr_match = re.search(r"\[USER\]\s*\n(.*)", text, re.DOTALL)

    if sys_match:
        parts.append(("system", sys_match.group(1).strip()))
    if usr_match:
        parts.append(("user", usr_match.group(1).strip()))

    if not parts:
        # 无标记, 整体作为 user
        parts.append(("user", text.strip()))

    return parts


def get_prompt(prompt_name: str, **variables) -> list[dict]:
    """获取 prompt 消息列表。

    Args:
        prompt_name: 逻辑名称(如 "slot_filling")
        **variables: 模板变量

    Returns:
        [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]

    Raises:
        FileNotFoundError: prompt 文件缺失
        KeyError: 必需变量未提供
    """
    _load_all()

    if prompt_name not in _CACHE:
        raise FileNotFoundError(f"prompt 未找到: {prompt_name}")

    raw = _CACHE[prompt_name]

    # 插值
    try:
        formatted = raw.format(**variables)
    except KeyError as e:
        raise KeyError(f"prompt {prompt_name} 缺少变量: {e}") from e

    # 解析为消息列表
    parts = _parse(formatted)
    return [{"role": role, "content": content} for role, content in parts]


def get_prompt_version(prompt_name: str) -> str:
    """获取当前使用的 prompt 版本号(如 'v1')。"""
    _load_all()
    versioned = _VERSION_MAP.get(prompt_name, prompt_name)
    # 提取版本号 (e.g. "slot_filling_v1" -> "v1")
    m = re.search(r"_(v\d+)$", versioned)
    return m.group(1) if m else "unknown"


def get_prompt_name_version(prompt_name: str) -> str:
    """获取 'name/v1' 格式的完整标识。"""
    return f"{prompt_name}/{get_prompt_version(prompt_name)}"


def list_prompts() -> list[dict]:
    """列出所有已加载的 prompt。"""
    _load_all()
    out = []
    for name, versioned in _VERSION_MAP.items():
        raw = _CACHE.get(name, "")
        # 提取关键约束
        constraints = []
        for pattern in [r"只输出\s*JSON", r"禁止.*?关键字", r"不要臆造", r"不要加免责声明",
                        r"只陈述数据.*不做评价", r"只用\s*SELECT", r"不要编造", r"不确定.*输出",
                        r"只在候选集内选择", r"必须来自原文", r"保守判断"]:
            if re.search(pattern, raw):
                constraints.append(pattern.replace(r".*?", "…").replace(r"\s", " "))
        out.append({
            "name": name,
            "version": get_prompt_version(name),
            "file": f"{versioned}.txt",
            "has_system": "[SYSTEM]" in raw,
            "constraints": constraints,
        })
    return out
