"""规则条款检索（scripts/query_rules.py）：索引完整性、关键词命中、
多关键词排序、--id 精确取、--list、退出码。

索引规模基准：rules/[0-9]*.md 共 20 个文件、568 条 `### R-XX-NN` 条款
（2026-10-13 复核，与 grep -c '^### R-' 对拍）。
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import query_rules as qr  # noqa: E402

CLAUSES = qr.load_index()
BY_ID = {c.rid: c for c in CLAUSES}


class TestIndexCompleteness:
    def test_clause_count_568(self):
        assert len(CLAUSES) == 568

    def test_ids_unique(self):
        assert len(BY_ID) == len(CLAUSES)

    def test_twenty_files_covered(self):
        files = {c.file for c in CLAUSES}
        assert len(files) == 20
        assert all(re.match(r"^[0-9].*\.md$", f) for f in files)

    def test_every_clause_has_title_body_line(self):
        for c in CLAUSES:
            assert c.title and c.body and c.line >= 1, c.rid

    def test_line_points_at_header(self):
        """抽样核对：条款行号精确指向源文件的 ### 头部行。"""
        for rid in ("R-纲-00", "R-运-32", "R-煞-04", "R-附-24"):
            c = BY_ID[rid]
            src = (ROOT / "rules" / c.file).read_text(encoding="utf-8").splitlines()
            assert src[c.line - 1].startswith(f"### {rid} ")

    def test_body_excludes_next_heading_and_separator(self):
        """正文截断于下一个 ##/### 标题，尾部 --- 分隔线剥除。"""
        c = BY_ID["R-纲-03"]
        assert "R-纲-04" not in c.body and "## 3." not in c.body
        assert not c.body.rstrip().endswith("---")
        last = BY_ID["R-运-39"]  # 文件尾条款：截到 EOF
        assert "五组引动清单照常逐组核查" in last.body
        assert last.body.rstrip().endswith("（综括，无单一原文）")


class TestSearch:
    def test_single_keyword_hit(self):
        hits = qr.search(CLAUSES, ["天乙贵人"])
        assert hits and hits[0].rid == "R-煞-04"
        assert hits[0].file == "94_神煞细节.md"

    def test_no_match_returns_empty(self):
        assert qr.search(CLAUSES, ["不存在词xyz"]) == []

    def test_multi_keyword_all_hits_rank_first(self):
        """全命中条款一律排在部分命中之前。"""
        hits = qr.search(CLAUSES, ["冲", "婚姻宫"])
        n_kw = 2
        seq = [sum(1 for kw in ("冲", "婚姻宫") if kw in c.title or kw in c.body)
               for c in hits]
        assert seq == sorted(seq, reverse=True)
        assert seq[0] == n_kw and hits[0].rid == "R-事-13"
        assert n_kw in seq  # 确有全命中条款

    def test_rare_keyword_outranks_common(self):
        """IDF：罕见词（从格）的强命中应压过常见词（破格）的弱命中。"""
        hits = qr.search(CLAUSES, ["从格", "破格"])
        assert hits[0].rid == "R-杂-38"

    def test_title_match_weighted(self):
        """标题命中加权：标题含「墓库」的两条排在仅正文提及者之前。"""
        hits = qr.search(CLAUSES, ["墓库"])
        assert {h.rid for h in hits[:2]} == {"R-附-18", "R-纲-11"}
        assert all("墓库" in h.title for h in hits[:2])

    def test_strict_and(self):
        hits = qr.search(CLAUSES, ["冲", "婚姻宫"], strict_and=True)
        assert hits and all("冲" in c.title + c.body and "婚姻宫" in c.title + c.body
                            for c in hits)
        assert qr.search(CLAUSES, ["从格", "破格"], strict_and=True) == []


class TestMainCLI:
    def test_search_exit0_and_output(self, capsys):
        assert qr.main(["天乙贵人", "--limit", "3"]) == 0
        out = capsys.readouterr().out
        assert "## R-煞-04　天乙贵人" in out
        assert "94_神煞细节.md:" in out

    def test_id_exact(self, capsys):
        assert qr.main(["--id", "R-运-32"]) == 0
        out = capsys.readouterr().out
        assert "## R-运-32　落地义务与候选收敛" in out
        assert "90_行运.md:352" in out

    def test_id_unknown_exit1(self, capsys):
        assert qr.main(["--id", "R-运-99"]) == 1
        assert "无命中" in capsys.readouterr().err

    def test_no_result_exit1(self, capsys):
        assert qr.main(["不存在词xyz"]) == 1
        capsys.readouterr()

    def test_no_input_exit2(self, capsys):
        assert qr.main([]) == 2
        assert "ERROR" in capsys.readouterr().err

    def test_list(self, capsys):
        assert qr.main(["--list"]) == 0
        out = capsys.readouterr().out
        assert "（568 条）" in out
        assert len(re.findall(r"^- R-\S+　", out, re.M)) == 568

    def test_limit(self, capsys):
        assert qr.main(["冲", "--limit", "2"]) == 0
        out = capsys.readouterr().out
        assert len(re.findall(r"^## R-", out, re.M)) == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
