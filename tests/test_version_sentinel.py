"""历法库版本哨兵（设计文档 §6.2 / §7）。

tyme4py 用 ==1.5.0 精确锁定：历表数据随版本漂移，库升级导致回归时
本测试第一时间定位，并提醒重新验证全部黄金样本。
"""
import unittest

import tyme4py


class TymeVersionSentinelTest(unittest.TestCase):
    def test_tyme4py_version_locked(self):
        self.assertEqual(
            tyme4py.__version__,
            "1.5.0",
            "tyme4py 版本漂移：升级后必须重新验证全部黄金样本，"
            "确认后再同步本断言",
        )


if __name__ == "__main__":
    unittest.main()
