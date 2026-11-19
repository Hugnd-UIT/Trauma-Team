import os
import sys
import struct
import unittest
import importlib
from pathlib import Path

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

detect = importlib.import_module("src.detect")
router = importlib.import_module("file-systems.router")
disk_read = importlib.import_module("tools.disk-read")

DELETED_TARGETS = {
    "docs/tests.docx",
    "docs/tests.txt",
    "images/tests.jpg",
    "srcs/c/tests.c",
    "srcs/python/tests.py",
    "tests.pptx",
    "tests.xlsx",
    "tests.zip"
}


def get_default_data_dir():
    base = Path(__file__).resolve().parent / "data"
    return base


def get_data_tree(data_dir=None):
    if data_dir is None:
        data_dir = get_default_data_dir()
    data_dir = Path(data_dir).resolve()
    tree = {}
    for root_d, dirs, files in os.walk(data_dir):
        rel = Path(root_d).relative_to(data_dir).as_posix()
        if rel == ".":
            rel = ""
        tree[rel] = {"dirs": sorted(dirs), "files": sorted(files)}
    return tree, data_dir


def create_lfn_entries(long_name):
    chunks = [long_name[i:i + 13] for i in range(0, len(long_name), 13)]
    entries = []
    for seq, chunk in enumerate(chunks, 1):
        is_last = (seq == len(chunks))
        entry = bytearray(32)
        entry[0] = seq | (0x40 if is_last else 0)
        entry[0x0B] = 0x0F
        raw_chars = chunk.encode("utf-16le")
        if len(chunk) < 13:
            raw_chars += b"\x00\x00" + b"\xff\xff" * (12 - len(chunk))
        entry[1:11] = raw_chars[0:10]
        entry[14:26] = raw_chars[10:22]
        entry[28:32] = raw_chars[22:26]
        entries.append(bytes(entry))
    return list(reversed(entries))


def make_83_name(name, is_dir=False):
    if "." in name and not is_dir:
        base, ext = name.rsplit(".", 1)
        base = base.replace(".", "_")
    else:
        base, ext = name, ""
    base = (base[:8]).upper().ljust(8)
    ext = (ext[:3]).upper().ljust(3)
    return base.encode("ascii", errors="replace")[:8] + ext.encode("ascii", errors="replace")[:3]


def make_fat_entry(name, cluster, size, is_dir=False, is_fat32=False, deleted=False):
    lfn = create_lfn_entries(name)
    s83 = bytearray(32)
    s83[0:11] = make_83_name(name, is_dir)
    if deleted:
        s83[0] = 0xE5
    s83[0x0B] = 0x10 if is_dir else 0x20
    if is_fat32:
        struct.pack_into("<H", s83, 0x14, (cluster >> 16) & 0xFFFF)
    struct.pack_into("<H", s83, 0x1A, cluster & 0xFFFF)
    struct.pack_into("<I", s83, 0x1C, size if not is_dir else 0)
    out = bytearray()
    for e in lfn:
        out.extend(e)
    out.extend(s83)
    return bytes(out)


def build_fat12(out_path="fat12.img", data_dir=None):
    tree, data_dir = get_data_tree(data_dir)
    total_size = 48 * 1024 * 1024
    bps = 512
    spc = 32
    csize = bps * spc
    res = 1
    fats = 2
    entries = 512
    spf = 16
    rdet_lba = res + fats * spf
    rdet_sec = (entries * 32 + bps - 1) // bps
    data_lba = rdet_lba + rdet_sec

    disk = bytearray(total_size)
    disk[510:512] = b"\x55\xaa"
    disk[3:11] = b"MSDOS5.0"
    struct.pack_into("<H", disk, 0x0B, bps)
    disk[0x0D] = spc
    struct.pack_into("<H", disk, 0x0E, res)
    disk[0x10] = fats
    struct.pack_into("<H", disk, 0x11, entries)
    struct.pack_into("<H", disk, 0x13, 0)
    disk[0x15] = 0xF0
    struct.pack_into("<H", disk, 0x16, spf)
    disk[0x36:0x3E] = b"FAT12   "

    cur_cluster = 2
    dir_clusters = {}
    for d in sorted(tree.keys()):
        if d != "":
            dir_clusters[d] = cur_cluster
            cur_cluster += 1

    file_clusters = {}
    file_sizes = {}
    for d, content in tree.items():
        for f in content["files"]:
            rel_f = f"{d}/{f}" if d else f
            abs_p = data_dir / rel_f
            with open(abs_p, "rb") as fp:
                data = fp.read()
            sz = len(data)
            file_sizes[rel_f] = sz
            file_clusters[rel_f] = cur_cluster
            num_c = max(1, (sz + csize - 1) // csize)
            off = (data_lba + (cur_cluster - 2) * spc) * bps
            disk[off:off + sz] = data
            cur_cluster += num_c

    for d, content in tree.items():
        ent_bytes = bytearray()
        for sub in content["dirs"]:
            sub_rel = f"{d}/{sub}" if d else sub
            ent_bytes.extend(make_fat_entry(sub, dir_clusters[sub_rel], 0, is_dir=True))
        for f in content["files"]:
            rel_f = f"{d}/{f}" if d else f
            is_del = rel_f in DELETED_TARGETS
            ent_bytes.extend(make_fat_entry(f, file_clusters[rel_f], file_sizes[rel_f], is_dir=False, deleted=is_del))
        if d == "":
            rdet_off = rdet_lba * bps
            disk[rdet_off:rdet_off + len(ent_bytes)] = ent_bytes
        else:
            c_off = (data_lba + (dir_clusters[d] - 2) * spc) * bps
            disk[c_off:c_off + len(ent_bytes)] = ent_bytes

    with open(out_path, "wb") as f:
        f.write(disk)
    return out_path


def build_fat16(out_path="fat16.img", data_dir=None):
    if data_dir is None:
        data_dir = get_default_data_dir()
    data_dir = Path(data_dir).resolve()
    total_size = 20 * 1024 * 1024
    disk = bytearray(total_size)

    offset = 4096
    carve_files = ["images/tests.png", "images/tests.jpg", "docs/tests.pdf", "docs/tests.docx", "tests.zip"]
    for rel_p in carve_files:
        abs_p = data_dir / rel_p
        if abs_p.exists():
            with open(abs_p, "rb") as fp:
                raw = fp.read()
            disk[offset:offset + len(raw)] = raw
            offset += ((len(raw) + 4095) // 4096) * 4096 + 4096

    with open(out_path, "wb") as f:
        f.write(disk)
    return out_path


def build_fat32(out_path="fat32.img", data_dir=None):
    tree, data_dir = get_data_tree(data_dir)
    total_size = 70 * 1024 * 1024
    bps = 512
    spc = 8
    csize = bps * spc
    res = 32
    fats = 2
    spf = 128
    root = 2
    data_lba = res + fats * spf

    disk = bytearray(total_size)
    disk[510:512] = b"\x55\xaa"
    disk[3:11] = b"MSDOS5.0"
    struct.pack_into("<H", disk, 0x0B, bps)
    disk[0x0D] = spc
    struct.pack_into("<H", disk, 0x0E, res)
    disk[0x10] = fats
    struct.pack_into("<I", disk, 0x20, total_size // bps)
    struct.pack_into("<I", disk, 0x24, spf)
    struct.pack_into("<I", disk, 0x2C, root)
    disk[0x52:0x5A] = b"FAT32   "

    fat1_off = res * bps
    fat2_off = (res + spf) * bps

    def set_fat(c, val):
        for fo in (fat1_off, fat2_off):
            struct.pack_into("<I", disk, fo + c * 4, val)

    set_fat(0, 0x0FFFFFF8)
    set_fat(1, 0x0FFFFFFF)
    set_fat(root, 0x0FFFFFFF)

    cur_cluster = 3
    dir_clusters = {"": root}
    for d in sorted(tree.keys()):
        if d != "":
            dir_clusters[d] = cur_cluster
            set_fat(cur_cluster, 0x0FFFFFFF)
            cur_cluster += 1

    file_clusters = {}
    file_sizes = {}
    blocker_mark = b"CORRUPTED_BLOCKER_DATA_ZEROED\x00"
    for d, content in tree.items():
        for f in content["files"]:
            rel_f = f"{d}/{f}" if d else f
            abs_p = data_dir / rel_f
            with open(abs_p, "rb") as fp:
                data = fp.read()
            sz = len(data)
            file_sizes[rel_f] = sz
            file_clusters[rel_f] = cur_cluster
            num_c = max(1, (sz + csize - 1) // csize)
            is_del = rel_f in DELETED_TARGETS

            if is_del and num_c > 1:
                half_c = max(1, num_c // 2)
                p1_sz = half_c * csize
                off1 = (data_lba + (cur_cluster - 2) * spc) * bps
                disk[off1:off1 + min(len(data), p1_sz)] = data[:p1_sz]
                blocker_c = cur_cluster + half_c
                blocker_off = (data_lba + (blocker_c - 2) * spc) * bps
                disk[blocker_off:blocker_off + len(blocker_mark)] = blocker_mark
                c2 = blocker_c + 1
                off2 = (data_lba + (c2 - 2) * spc) * bps
                disk[off2:off2 + len(data[p1_sz:])] = data[p1_sz:]
                cur_cluster = c2 + (num_c - half_c)
            else:
                off = (data_lba + (cur_cluster - 2) * spc) * bps
                disk[off:off + sz] = data
                if not is_del:
                    for i in range(num_c - 1):
                        set_fat(cur_cluster + i, cur_cluster + i + 1)
                    set_fat(cur_cluster + num_c - 1, 0x0FFFFFFF)
                cur_cluster += num_c

    for d, content in tree.items():
        ent_bytes = bytearray()
        for sub in content["dirs"]:
            sub_rel = f"{d}/{sub}" if d else sub
            ent_bytes.extend(make_fat_entry(sub, dir_clusters[sub_rel], 0, is_dir=True, is_fat32=True))
        for f in content["files"]:
            rel_f = f"{d}/{f}" if d else f
            is_del = rel_f in DELETED_TARGETS
            ent_bytes.extend(make_fat_entry(f, file_clusters[rel_f], file_sizes[rel_f], is_dir=False, is_fat32=True, deleted=is_del))
        c_off = (data_lba + (dir_clusters[d] - 2) * spc) * bps
        disk[c_off:c_off + len(ent_bytes)] = ent_bytes

    with open(out_path, "wb") as f:
        f.write(disk)
    return out_path


def encode_ntfs_runs(runs):
    out = bytearray()
    cur_lcn = 0
    for rlen, lcn in runs:
        diff = lcn - cur_lcn
        cur_lcn = lcn
        len_b = rlen.to_bytes((rlen.bit_length() + 8) // 8 or 1, "little", signed=False)
        diff_b = diff.to_bytes((diff.bit_length() + 8) // 8 or 1, "little", signed=True)
        header_byte = (len(diff_b) << 4) | len(len_b)
        out.append(header_byte)
        out.extend(len_b)
        out.extend(diff_b)
    out.append(0)
    return bytes(out)


def make_ntfs_fn_attr(filename, parent_id):
    fn_raw = filename.encode("utf-16le")
    fn_data_len = 66 + len(fn_raw)
    content = bytearray(fn_data_len)
    content[0:6] = parent_id.to_bytes(6, "little")
    content[0x40] = len(filename)
    content[0x41] = 1
    content[0x42:0x42 + len(fn_raw)] = fn_raw
    c_off = 24
    attr_len = (c_off + fn_data_len + 7) & ~7
    attr = bytearray(attr_len)
    struct.pack_into("<I", attr, 0, 0x30)
    struct.pack_into("<I", attr, 4, attr_len)
    attr[8] = 0
    struct.pack_into("<I", attr, 0x10, fn_data_len)
    struct.pack_into("<H", attr, 0x14, c_off)
    attr[c_off:c_off + fn_data_len] = content
    return attr


def make_ntfs_data_attr(size, runs, csize):
    run_bytes = encode_ntfs_runs(runs)
    total_clusters = sum(r[0] for r in runs)
    attr_len = (64 + len(run_bytes) + 7) & ~7
    attr = bytearray(attr_len)
    struct.pack_into("<I", attr, 0, 0x80)
    struct.pack_into("<I", attr, 4, attr_len)
    attr[8] = 1
    struct.pack_into("<H", attr, 16, 0)
    struct.pack_into("<Q", attr, 24, total_clusters - 1)
    struct.pack_into("<H", attr, 32, 64)
    struct.pack_into("<Q", attr, 40, total_clusters * csize)
    struct.pack_into("<Q", attr, 48, size)
    struct.pack_into("<Q", attr, 56, size)
    attr[64:64 + len(run_bytes)] = run_bytes
    return attr


def make_ntfs_record(rec_id, filename, parent_id, size=0, runs=None, is_dir=False, csize=4096, deleted=False):
    rec = bytearray(1024)
    rec[:4] = b"FILE"
    struct.pack_into("<H", rec, 4, 0x2A)
    struct.pack_into("<H", rec, 6, 3)
    struct.pack_into("<Q", rec, 8, 1)
    struct.pack_into("<H", rec, 0x14, 0x38)
    if is_dir:
        flags = 2 if deleted else 3
    else:
        flags = 0 if deleted else 1
    struct.pack_into("<H", rec, 0x16, flags)
    struct.pack_into("<I", rec, 0x18, 1024)
    struct.pack_into("<I", rec, 0x1C, 1024)
    struct.pack_into("<I", rec, 0x2C, rec_id)

    fn_attr = make_ntfs_fn_attr(filename, parent_id)
    pos = 0x38
    rec[pos:pos + len(fn_attr)] = fn_attr
    pos += len(fn_attr)

    if not is_dir and runs is not None:
        data_attr = make_ntfs_data_attr(size, runs, csize)
        rec[pos:pos + len(data_attr)] = data_attr
        pos += len(data_attr)

    struct.pack_into("<I", rec, pos, 0xFFFFFFFF)
    return bytes(rec)


def build_ntfs(out_path="ntfs.img", data_dir=None):
    if data_dir is None:
        data_dir = get_default_data_dir()
    data_dir = Path(data_dir).resolve()
    total_size = 20 * 1024 * 1024
    disk = bytearray(total_size)
    disk[510:512] = b"\x55\xaa"
    disk[3:11] = b"NTFS    "
    struct.pack_into("<H", disk, 0x0B, 512)
    disk[0x0D] = 8
    struct.pack_into("<q", disk, 0x30, 2000)

    recs = [
        make_ntfs_record(16, "tests.docx", 5, size=1026736, runs=[(251, 50)], is_dir=False, deleted=True),
        make_ntfs_record(17, "tests.pdf", 5, size=180748, runs=[(45, 350)], is_dir=False, deleted=False),
        make_ntfs_record(18, "tests.jpg", 5, size=36212, runs=[(9, 420)], is_dir=False, deleted=True),
        make_ntfs_record(19, "tests.c", 5, size=1787931, runs=[(437, 500)], is_dir=False, deleted=True)
    ]
    sec_offsets = [51200, 53248, 55296, 57344]
    for r, sec_off in zip(recs, sec_offsets):
        disk[sec_off:sec_off + 1024] = r

    with open(out_path, "wb") as f:
        f.write(disk)
    return out_path


def build_all(data_dir=None):
    f12 = build_fat12("fat12.img", data_dir)
    f16 = build_fat16("fat16.img", data_dir)
    f32 = build_fat32("fat32.img", data_dir)
    ntfs = build_ntfs("ntfs.img", data_dir)
    return [f12, f16, f32, ntfs]


class TestDiskGeneration(unittest.TestCase):
    def test_build_and_detect_fat12(self):
        p = "fat12.img"
        build_fat12(p)
        self.assertTrue(os.path.exists(p))
        with disk_read.Disk(p) as d:
            info = detect.detect(d)
            self.assertEqual(info.get("fs"), "FAT12")
            items = router.scan(d, info)
            self.assertEqual(len(items), 33)
            del_count = sum(1 for it in items if it.get("deleted"))
            self.assertEqual(del_count, 8)

    def test_build_and_detect_fat16(self):
        p = "fat16.img"
        build_fat16(p)
        self.assertTrue(os.path.exists(p))
        with disk_read.Disk(p) as d:
            info = detect.detect(d)
            self.assertEqual(info.get("fs"), "UNKNOWN")
            items = router.scan(d, info)
            self.assertTrue(len(items) >= 4)
            self.assertTrue(all(it.get("carved") for it in items))

    def test_build_and_detect_fat32(self):
        p = "fat32.img"
        build_fat32(p)
        self.assertTrue(os.path.exists(p))
        with disk_read.Disk(p) as d:
            info = detect.detect(d)
            self.assertEqual(info.get("fs"), "FAT32")
            items = router.scan(d, info)
            self.assertEqual(len(items), 33)
            del_items = [it for it in items if it.get("deleted")]
            self.assertEqual(len(del_items), 8)
            del_c = del_items[0]["cluster"]
            fat_off = info["res"] * info["bps"] + del_c * 4
            fat_val = struct.unpack_from("<I", d.read(fat_off, 4))[0]
            self.assertEqual(fat_val, 0)

    def test_build_and_detect_ntfs(self):
        p = "ntfs.img"
        build_ntfs(p)
        self.assertTrue(os.path.exists(p))
        with disk_read.Disk(p) as d:
            info = detect.detect(d)
            items = router.scan(d, info)
            self.assertEqual(len(items), 4)
            names = [it["name"] for it in items]
            self.assertIn("tests.docx", names)
            self.assertIn("tests.pdf", names)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("build", "--build"):
        paths = build_all()
        for p in paths:
            print(f"Generated: {p} ({os.path.getsize(p)} bytes)")
    else:
        unittest.main(verbosity=2)
