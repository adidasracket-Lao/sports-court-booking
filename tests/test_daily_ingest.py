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


import shutil
import tempfile
import unittest.mock

import daily_ingest
from daily_ingest import (
    make_filename, csv_line, known_receipt_ids, append_csv_lines,
    sha1_of, list_new_images, load_state, save_state, ingest,
)


class FilenameCsvTest(unittest.TestCase):
    def test_make_filename(self):
        parsed = {"receipt_id": "IDOB260712073004WXI", "date": "2026/7/15"}
        self.assertEqual(make_filename(parsed, ".jpg"), "20260715_IDOB260712073004WXI.jpg")

    def test_csv_line(self):
        parsed = {"receipt_id": "IDOBX", "date": "2026/7/15", "time": "20:00~21:00",
                  "court": "羽毛球7號場", "renter_code": "9761", "extra_code": "6175"}
        self.assertEqual(
            csv_line(parsed, "20260715_IDOBX.jpg"),
            "2026/7/15 20:00~21:00,羽毛球7號場,9761,6175,,,20260715_IDOBX.jpg")


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "cache").mkdir()
        (self.tmp / "uploads").mkdir()
        (self.tmp / "state").mkdir()
        self.csv_path = self.tmp / "manual.csv"
        header = "使用時間,場地編號,租場者,額外取場者,租場者(姓名）,額外取場者（姓名）,source\r\n"
        self.csv_path.write_bytes(b"\xef\xbb\xbf" + header.encode("utf-8"))
        self.patches = [
            unittest.mock.patch.object(daily_ingest, "CACHE_DIR", self.tmp / "cache"),
            unittest.mock.patch.object(daily_ingest, "UPLOAD_DIR", self.tmp / "uploads"),
            unittest.mock.patch.object(daily_ingest, "MANUAL_CSV", self.csv_path),
            unittest.mock.patch.object(daily_ingest, "STATE_FILE", self.tmp / "state" / "state.json"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def test_append_csv_keeps_bom_and_crlf(self):
        append_csv_lines(["2026/7/15 20:00~21:00,羽毛球7號場,9761,6175,,,x.jpg"])
        raw = self.csv_path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(raw.endswith(b"x.jpg\r\n"))
        # 不得有裸 LF（全部行尾都是 CRLF）
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))

    def test_known_receipt_ids_reads_source_column(self):
        append_csv_lines(["2026/7/15 20:00~21:00,,,,,,20260715_IDOBAAA111222333.jpg"])
        self.assertIn("IDOBAAA111222333", known_receipt_ids())

    def test_ingest_dedups_and_copies(self):
        # 兩張同收據圖 + 一張無關圖
        (self.tmp / "cache" / "a.jpg").write_bytes(b"fake-image-1")
        (self.tmp / "cache" / "b.jpg").write_bytes(b"fake-image-2")
        (self.tmp / "cache" / "c.jpg").write_bytes(b"cat-photo")
        ocr_map = {
            "a.jpg": "收據編號: IDOB260714073001ABC\n使用日期: 2026-07-16\n使用時段: 19:00~20:00\n場區編號: 羽毛球3號場\n租場者: ****1234\n額外取場者: ****5678",
            "b.jpg": "收據編號: IDOB260714073001ABC\n使用日期: 2026-07-16",  # 同收據、欄位較少
            "c.jpg": "風景照",
        }
        with unittest.mock.patch.object(daily_ingest, "ocr_cache_image",
                                        side_effect=lambda p: ocr_map[p.name]):
            report = ingest(dry_run=False)
        self.assertEqual(len(report["added"]), 1)
        self.assertTrue((self.tmp / "uploads" / "20260716_IDOB260714073001ABC.jpg").exists())
        content = self.csv_path.read_text(encoding="utf-8-sig")
        self.assertIn("2026/7/16 19:00~20:00,羽毛球3號場,1234,5678,,,20260716_IDOB260714073001ABC.jpg", content)
        # state 記錄了 3 個 hash，重跑不再有新圖
        with unittest.mock.patch.object(daily_ingest, "ocr_cache_image",
                                        side_effect=lambda p: ocr_map[p.name]):
            report2 = ingest(dry_run=False)
        self.assertEqual(report2["added"], [])

    def test_ingest_flags_suspect_without_receipt_id(self):
        (self.tmp / "cache" / "bad.jpg").write_bytes(b"blurry")
        with unittest.mock.patch.object(daily_ingest, "ocr_cache_image",
                                        return_value="體育局 使用時段 糊到讀不到編號"):
            report = ingest(dry_run=False)
        self.assertEqual(report["added"], [])
        self.assertEqual(report["suspects"], ["bad.jpg"])

    def test_ingest_skips_receipt_already_in_csv(self):
        append_csv_lines(["2026/7/16 19:00~20:00,羽毛球3號場,1234,5678,,,20260716_IDOB260714073001ABC.jpg"])
        (self.tmp / "cache" / "dup.jpg").write_bytes(b"same-receipt-again")
        with unittest.mock.patch.object(daily_ingest, "ocr_cache_image",
                                        return_value="收據編號: IDOB260714073001ABC\n使用日期: 2026-07-16\n使用時段: 19:00~20:00"):
            report = ingest(dry_run=False)
        self.assertEqual(report["added"], [])


if __name__ == "__main__":
    unittest.main()
