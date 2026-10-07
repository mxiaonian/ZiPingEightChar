# vendor/ —— 随包内置的依赖（免安装）

用户拿到 skill 后**无需 pip install**：运行期依赖的源码直接放在这里，
`scripts/cast_chart.py` 启动时把本目录插入 `sys.path` 最前（优先于环境已安装的包）。

## 内容

| 目录/文件 | 包 | 版本 | 来源 | 许可证 |
|---|---|---|---|---|
| `tyme4py/` | tyme4py | 1.5.0（==锁定） | PyPI / 工作区 `tyme4py-1.5.0/` | MIT（`tyme4py.LICENSE`） |
| `tzdata/` | tzdata | 2026.5 | PyPI | Apache-2.0（`tzdata.LICENSE`） |

两个包均为纯 Python / 纯数据，无编译产物，跨平台（macOS / Linux / Windows）、
跨架构可用。运行时唯一要求是 **Python ≥ 3.10**（`zoneinfo` 与类型标注语法需要）。

## 为什么 vendor 而不是打包 .venv

虚拟环境不可移植：`pyvenv.cfg` 与 activate 脚本硬编码创建时的绝对路径，
`bin/python` 是指向本机解释器的符号链接，且按 OS/架构绑定。
vendor 纯源码没有这些问题，同时把 `tyme4py==1.5.0` 的版本锁定做到了字节级。

## 如何升级

1. 用新版本源码替换对应目录（保持目录名不变）；
2. 同步更新本表的版本号与 `pyproject.toml` / `requirements.txt` 的锁定；
3. 跑 `tests/` 黄金样本与规则库 `rules/tests/` 确认无回归
   （历法库升级可能改变节气时刻，必须全量回归）。
