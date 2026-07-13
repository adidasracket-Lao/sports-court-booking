import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from generate_data import ManualRow, match_manual_row


def make_row(**kw):
    defaults = dict(date="2026/7/15", time="18:00~19:00", court="羽毛球5號場",
                    renter_code="7836", extra_code="8317",
                    renter_name="", extra_name="", source="")
    defaults.update(kw)
    return ManualRow(**defaults)


class MatchManualRowTest(unittest.TestCase):
    def test_exact_source_match_wins(self):
        rows = [make_row(source="a.jpg", court="羽毛球1號場"),
                make_row(source="b.jpg", court="羽毛球2號場")]
        parsed = {"sourceFile": "b.jpg", "date": "", "time": "", "court": "",
                  "renter_code": "", "extra_code": ""}
        self.assertIs(match_manual_row(parsed, rows), rows[1])

    def test_score_fallback_skips_rows_with_source(self):
        # 行有 source 但檔名不同 → 即使欄位全中也不得配對（防錯位）
        rows = [make_row(source="other.jpg")]
        parsed = {"sourceFile": "new.jpg", "date": "2026/7/15",
                  "time": "18:00~19:00", "court": "羽毛球5號場",
                  "renter_code": "7836", "extra_code": "8317"}
        self.assertIsNone(match_manual_row(parsed, rows))

    def test_score_fallback_matches_sourceless_row(self):
        rows = [make_row(source="")]
        parsed = {"sourceFile": "new.jpg", "date": "2026/7/15",
                  "time": "18:00~19:00", "court": "羽毛球5號場",
                  "renter_code": "7836", "extra_code": "8317"}
        self.assertIs(match_manual_row(parsed, rows), rows[0])


if __name__ == "__main__":
    unittest.main()
