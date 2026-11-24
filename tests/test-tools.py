import os
import sys
import shutil
import hashlib
import unittest
import importlib
import io
import struct
import zipfile

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

disk_read = importlib.import_module("tools.disk-read")
hex_search = importlib.import_module("tools.hex-search")
file_valid = importlib.import_module("tools.file-valid")
file_read = importlib.import_module("tools.file-read")
file_export = importlib.import_module("tools.file-export")


class TestTools(unittest.TestCase):

    def setUp(self):
        self.temp_dir = "tests_tools_scratch"
        os.makedirs(self.temp_dir, exist_ok=True)
        self.dummy_disk_path = os.path.join(self.temp_dir, "virtual_disk.bin")

        dummy_content = b"FORENSIC_HEADER_TEST\n" + b"X" * 2000
        with open(self.dummy_disk_path, "wb") as f:
            f.write(dummy_content)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_disk_read_capabilities(self):
        disk = disk_read.Disk(self.dummy_disk_path)
        self.assertEqual(disk.size(), os.path.getsize(self.dummy_disk_path))

        header_bytes = disk.read(0, 20)
        self.assertEqual(header_bytes, b"FORENSIC_HEADER_TEST")

        empty_read = disk.read(99999, 512)
        self.assertEqual(empty_read, b"")
        disk.close()

    def test_hex_search_entropy_and_pattern(self):
        zero_bytes = b"\x00" * 512
        self.assertEqual(hex_search.entropy(zero_bytes), 0.0)

        c_code_sample = b"int main() { printf('Trauma Team'); return 0; }\n" * 10
        calc_entropy = hex_search.entropy(c_code_sample)
        self.assertGreaterEqual(calc_entropy, 3.2)
        self.assertLessEqual(calc_entropy, 6.5)

        disk = disk_read.Disk(self.dummy_disk_path)
        hits = hex_search.search_pattern(disk, "HEADER", max_results=1)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0], 9)
        disk.close()

    def test_file_validation_syntax(self):
        valid_bracket_code = "void init{ if (1) { return; } }"
        is_ok, err = file_valid.check_brackets(valid_bracket_code)
        self.assertTrue(is_ok)

        unmatched_bracket = "void error{ return; } }"
        is_ok, err = file_valid.check_brackets(unmatched_bracket)
        self.assertFalse(is_ok)
        self.assertIn("Unmatched", err)

        valid_python = b"def calculate(value):\n    return value * 2\n"
        py_ok, _ = file_valid.validate(valid_python, "py")
        self.assertTrue(py_ok)

        valid_c = b"int compute(int x) { return x + 1; }"
        c_ok, _ = file_valid.validate(valid_c, "c")
        self.assertTrue(c_ok)

        cpp_code = b"namespace Trauma { class Worker { public: int id; }; }"
        c_with_cpp_ok, _ = file_valid.validate(cpp_code, "c")
        self.assertFalse(c_with_cpp_ok)
        cpp_ok, _ = file_valid.validate(cpp_code, "cpp")
        self.assertTrue(cpp_ok)

    def test_file_export_payload_and_hash(self):
        test_payload = b"int main() { return 0; }\n" + b"\x00" * 200
        target_size = 25
        out_directory = os.path.join(self.temp_dir, "recovered")

        result = file_export.save(
            data=test_payload,
            filename="_TARGET.C",
            size=target_size,
            out_dir=out_directory,
            chain=[10, 12]
        )

        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(result.get("size"), target_size)

        expected_slice = test_payload[:target_size]
        expected_sha = hashlib.sha256(expected_slice).hexdigest()
        self.assertEqual(result.get("sha256"), expected_sha)

    def test_binary_format_validation(self):
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, "w") as zf:
            zf.writestr("word/document.xml", "<w:p>test</w:p>")
        docx_bytes = bio.getvalue()
        ok_zip, _ = file_valid.validate_zip(docx_bytes)
        self.assertTrue(ok_zip)
        ok_docx, _ = file_valid.validate(docx_bytes, "docx")
        self.assertTrue(ok_docx)

        png_bytes = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 0) + b"IEND\xaeB`\x82"
        ok_png, _ = file_valid.validate_png(png_bytes)
        self.assertTrue(ok_png)

        jpg_bytes = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xFF\xD9"
        ok_jpg, _ = file_valid.validate_jpg(jpg_bytes)
        self.assertTrue(ok_jpg)

        pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
        ok_pdf, _ = file_valid.validate_pdf(pdf_bytes)
        self.assertTrue(ok_pdf)

        ole_bytes = bytearray(1024)
        ole_bytes[:8] = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"
        struct.pack_into("<H", ole_bytes, 0x1E, 9)
        ok_ole, _ = file_valid.validate_ole(bytes(ole_bytes))
        self.assertTrue(ok_ole)

    def test_file_read_execution(self):
        disk = disk_read.Disk(self.dummy_disk_path)
        info = {"data_lba": 0, "spc": 1, "bps": 512}

        res_tail = file_read.execute(disk, info, {"chain": [2], "mode": "tail", "count": 1})
        self.assertIn("File content of clusters [2]", res_tail)

        res_head = file_read.execute(disk, info, {"chain": [2, 3], "mode": "head", "count": 1})
        self.assertIn("File content of clusters [2]", res_head)

        res_range = file_read.execute(disk, info, {"chain": [2, 3, 4], "mode": "range", "start_cluster": 2, "end_cluster": 3})
        self.assertIn("File content of clusters [2, 3]", res_range)

        res_err = file_read.execute(disk, info, {"chain": []})
        self.assertIn("Error: chain is empty", res_err)

        disk.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
