import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import generate_data
from generate_data import ManualRow, extract_codes, extract_court, match_manual_row


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


class ExtractCourtTest(unittest.TestCase):
    def test_explicit_court(self):
        self.assertEqual(extract_court("場區編號:羽毛球8號場"), "羽毛球8號場")

    def test_fallback_ignores_renter_code_line(self):
        # 場區編號讀不到時，不得把租場者代碼當場號
        text = "場區編 場\n租場者: 9409\n額外取場者: 1086"
        self.assertEqual(extract_court(text), "")

    def test_fallback_digits_attached_to_haochang(self):
        self.assertEqual(extract_court("亂碼 11號場 亂碼"), "羽毛球11號場")


class ExtractCodesTest(unittest.TestCase):
    def test_ocr_variant_chang(self):
        # 埸 為 場 的常見 OCR 誤讀
        codes = extract_codes("租埸者: 9709\n額外取場者: 0843")
        self.assertEqual(codes, ["9709", "0843"])


class BuildRecordsDedupeTest(unittest.TestCase):
    def test_dedupes_by_visible_slot_not_codes_or_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uploads = root / "uploads"
            uploads.mkdir()
            (uploads / "a.jpg").write_bytes(b"not a real image; OCR is mocked")
            (uploads / "b.jpg").write_bytes(b"not a real image; OCR is mocked")
            manual_csv = root / "manual.csv"
            manual_csv.write_text(
                "使用時間,場地編號,租場者,額外取場者,租場者(姓名）,額外取場者（姓名）,source\n"
                "2026/9/18 20:00~21:00,羽毛球6號場,9709,0843,,,a.jpg\n"
                "2026/9/18 20:00~21:00,羽毛球6號場,8970,0843,,,b.jpg\n",
                encoding="utf-8",
            )
            name_csv = root / "names.csv"
            name_csv.write_text("後四碼,取場人\n0843,Wing\n", encoding="utf-8")

            ocr_text = "使用日期: 2026-09-18\n使用時段: 20:00~21:00\n羽毛球6號場\n租場者: 9709\n額外取場者: 0843\n"
            with patch.object(generate_data, "UPLOAD_DIR", uploads), \
                 patch.object(generate_data, "MANUAL_CSV", manual_csv), \
                 patch.object(generate_data, "NAME_MAP_CSV", name_csv), \
                 patch.object(generate_data, "available_tesseract_languages", return_value=[]), \
                 patch.object(generate_data, "ocr_image", return_value=ocr_text):
                records = generate_data.build_records()["records"]

        slot_records = [
            record for record in records
            if (record["date"], record["time"], record["court"]) == ("2026/9/18", "20:00~21:00", "羽毛球6號場")
        ]
        self.assertEqual(len(slot_records), 1)
        self.assertEqual(slot_records[0]["renterCode"], "9709")


if __name__ == "__main__":
    unittest.main()
