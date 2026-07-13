import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from daily_ingest import extract_receipt_id, looks_like_receipt, parse_receipt, field_count

SAMPLE = """奧林匹克體育中心-羽毛球區
場區編號:羽毛球8號場
收據編號 : IDOB260711073009CKB
使用日期 : 2026-07-14 (=)
使用時段 : 19:00~20:00
租場者 :****1059
額外取場者 :****9963
"""


class ReceiptIdTest(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(extract_receipt_id(SAMPLE), "IDOB260711073009CKB")

    def test_ocr_one_for_i(self):
        self.assertEqual(extract_receipt_id("收據編號: 1DOB260712073009KG1"),
                         "IDOB260712073009KG1")

    def test_space_inside(self):
        self.assertEqual(extract_receipt_id("收據編號 : IDOB26071 2073004WXI"),
                         "IDOB260712073004WXI")

    def test_absent(self):
        self.assertEqual(extract_receipt_id("聯絡人頭像，無收據"), "")


class LooksLikeReceiptTest(unittest.TestCase):
    def test_keyword_hit(self):
        self.assertTrue(looks_like_receipt("...體育局...使用時段..."))

    def test_plain_photo(self):
        self.assertFalse(looks_like_receipt("風景照片"))


class ParseReceiptTest(unittest.TestCase):
    def test_full_parse(self):
        p = parse_receipt(SAMPLE)
        self.assertEqual(p["receipt_id"], "IDOB260711073009CKB")
        self.assertEqual(p["date"], "2026/7/14")
        self.assertEqual(p["time"], "19:00~20:00")
        self.assertEqual(p["court"], "羽毛球8號場")
        self.assertEqual(p["renter_code"], "1059")
        self.assertEqual(p["extra_code"], "9963")
        self.assertEqual(field_count(p), 5)

    def test_partial(self):
        p = parse_receipt("收據編號: IDOB260711073009CKB\n使用時段: 19:00~20:00")
        self.assertEqual(field_count(p), 1)


if __name__ == "__main__":
    unittest.main()
