import os
import sys
import struct
import unittest
import importlib

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src import detect
from src import build
router = importlib.import_module("file-systems.router")
fat32_info = importlib.import_module("file-systems.fat.fat32-info")
fat_info = importlib.import_module("file-systems.fat.fat-info")
ntfs_info = importlib.import_module("file-systems.ntfs.ntfs-info")
disk_read = importlib.import_module("tools.disk-read")


class DummyDisk:
    def __init__(self, data_dict, total_size=1048576):
        self.data_dict = data_dict
        self.total_size = total_size

    def size(self):
        return self.total_size

    def read(self, offset, size=512):
        if isinstance(self.data_dict, (bytes, bytearray)):
            return bytes(self.data_dict[offset:offset + size])
        if offset in self.data_dict:
            return self.data_dict[offset][:size]
        return b"\x00" * size

    def cluster(self, cluster_id, data_lba, sectors_per_cluster=2, bytes_per_sector=512):
        offset = (data_lba + (cluster_id - 2) * sectors_per_cluster) * bytes_per_sector
        return self.read(offset, sectors_per_cluster * bytes_per_sector)


class TestFileSystems(unittest.TestCase):

    def test_detect_all_filesystems(self):
        short_bytes = b"\x00" * 200
        result_short = detect.parse(short_bytes)
        self.assertEqual(result_short.get("fs"), "UNKNOWN")

        ntfs_sector = bytearray(512)
        ntfs_sector[3:11] = b"NTFS    "
        struct.pack_into("<H", ntfs_sector, 0x0B, 512)
        ntfs_sector[0x0D] = 8
        struct.pack_into("<q", ntfs_sector, 0x30, 4096)
        ntfs_sector[510:512] = b"\x55\xaa"
        result_ntfs = detect.parse(bytes(ntfs_sector))
        self.assertEqual(result_ntfs.get("fs"), "NTFS")
        self.assertEqual(result_ntfs.get("mft_cluster"), 4096)

        fat32_sector = bytearray(512)
        fat32_sector[0x52:0x5A] = b"FAT32   "
        struct.pack_into("<H", fat32_sector, 0x0B, 512)
        fat32_sector[0x0D] = 2
        struct.pack_into("<H", fat32_sector, 0x0E, 32)
        fat32_sector[0x10] = 2
        struct.pack_into("<I", fat32_sector, 0x24, 1024)
        fat32_sector[510:512] = b"\x55\xaa"
        result_fat32 = detect.parse(bytes(fat32_sector))
        self.assertEqual(result_fat32.get("fs"), "FAT32")

        fat16_sector = bytearray(512)
        fat16_sector[0x36:0x3E] = b"FAT16   "
        struct.pack_into("<H", fat16_sector, 0x0B, 512)
        fat16_sector[0x0D] = 4
        struct.pack_into("<H", fat16_sector, 0x0E, 1)
        struct.pack_into("<H", fat16_sector, 0x11, 512)
        fat16_sector[510:512] = b"\x55\xaa"
        result_fat16 = detect.parse(bytes(fat16_sector))
        self.assertEqual(result_fat16.get("fs"), "FAT16")

    def test_directory_tree_building(self):
        sample_items = [
            {"path": "/src/main.c", "is_dir": False, "size": 1024, "deleted": False},
            {"path": "/src/_trash.c", "is_dir": False, "size": 512, "deleted": True}
        ]
        tree = build.build_dict(sample_items)
        self.assertIn("src", tree["children"])
        self.assertIn("main.c", tree["children"]["src"]["children"])
        self.assertIn("_trash.c", tree["children"]["src"]["children"])
        rendered_lines = build.render(tree)
        self.assertTrue(len(rendered_lines) > 0)

    def test_fat32_scanner(self):
        lfn_entry = bytearray(32)
        lfn_entry[0] = 0x41
        lfn_entry[0x0B] = 0x0F
        lfn_entry[1:11] = "Docum".encode("utf-16le")
        lfn_entry[14:26] = "ent\x00\xff\xff".encode("utf-16le")
        lfn_entry[28:32] = "\xff\xff".encode("utf-16le")

        decoded = fat32_info.decode_lfn(bytes(lfn_entry))
        self.assertEqual(decoded, "Document")

    def test_fat16_scanner(self):
        lfn_entry = bytearray(32)
        lfn_entry[0] = 0x41
        lfn_entry[0x0B] = 0x0F
        lfn_entry[1:11] = "Notes".encode("utf-16le")
        lfn_entry[14:26] = ".txt\x00\xff".encode("utf-16le")
        lfn_entry[28:32] = "\xff\xff".encode("utf-16le")

        decoded = fat_info.decode_lfn(bytes(lfn_entry))
        self.assertEqual(decoded, "Notes.txt")

    def test_ntfs_scanner_data_runs(self):
        raw_runs = bytes([0x21, 0x04, 0x10, 0x00, 0x00])
        decoded_runs = ntfs_info.decode_runs(raw_runs, 0, len(raw_runs))
        self.assertEqual(len(decoded_runs), 1)
        self.assertEqual(decoded_runs[0], (4, 16))

    def test_ntfs_orphaned_carving(self):
        disk_bytes = bytearray(4096)
        rec = bytearray(1024)
        rec[:4] = b"FILE"
        struct.pack_into("<H", rec, 0x14, 0x30)
        struct.pack_into("<H", rec, 0x16, 0x01)
        fn_name = "server.c"
        fn_len = len(fn_name)
        total_fn_len = 0x18 + 0x42 + fn_len * 2
        fn_data = bytearray(total_fn_len)
        struct.pack_into("<II", fn_data, 0, 0x30, total_fn_len)
        struct.pack_into("<H", fn_data, 0x14, 0x18)
        fn_data[0x18 + 0x40] = fn_len
        fn_data[0x18 + 0x41] = 0x01
        for i, c in enumerate(fn_name):
            fn_data[0x18 + 0x42 + i * 2:0x18 + 0x42 + i * 2 + 2] = c.encode("utf-16le")
        rec[0x30:0x30 + total_fn_len] = fn_data
        disk_bytes[1024:2048] = rec
        dummy = DummyDisk(bytes(disk_bytes))
        records = ntfs_info.scan(dummy, {"fs": "NTFS", "bps": 512, "mft_lba": 9999})
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["name"], "server.c")

    def test_router_dispatch(self):
        dummy_disk = DummyDisk({})
        self.assertEqual(router.scan(dummy_disk, {"fs": "UNKNOWN"}), [])

        image_path = "test.img"
        if os.path.exists(image_path):
            disk = disk_read.Disk(image_path)
            info = detect.detect(disk)
            self.assertEqual(info.get("fs"), "FAT32")
            records = router.scan(disk, info)
            disk.close()
            self.assertGreater(len(records), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
