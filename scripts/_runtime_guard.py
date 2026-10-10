"""运行环境守卫：本技能脚本需要 Python ≥ 3.10。

各入口脚本在 sys.path 引导后立即 import 本模块（import 即检查，无其他调用）：
解释器低于 3.10 时在 stderr 打印中文提示并以退出码 3 结束，
避免用户看到库深处难以理解的报错（运行期 `X | None` 注解在 3.9 及以下
求值即 TypeError，报错位置离真正原因很远）。

本模块自身只用 Python 3.6 兼容语法，保证在旧解释器上也能正常执行检查。
"""
from __future__ import annotations

import sys

MIN_PYTHON = (3, 10)


def version_error(version_info=None) -> str | None:
    """版本达标返回 None；不足时返回中文报错文案。可注入 version_info 便于测试。"""
    vi = sys.version_info if version_info is None else version_info
    if tuple(vi[:2]) >= MIN_PYTHON:
        return None
    return (f"运行环境不可用：本技能脚本需要 Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} "
            f"或更高版本，当前解释器为 Python {vi[0]}.{vi[1]}.{vi[2]}"
            f"（{sys.executable}）。请改用更新版本的 Python 运行"
            "（macOS 系统自带 python3 为 3.9，不可用；可用 python3.11/3.12/3.13 "
            "或项目自带虚拟环境）。")


_msg = version_error()
if _msg is not None:
    print(f"ERROR: {_msg}", file=sys.stderr)
    raise SystemExit(3)
