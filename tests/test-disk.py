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
parse_mod = importlib.import_module("src.parse")
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


def get_data_tree(data_dir=None, files_subset=None):
    if data_dir is None:
        data_dir = get_default_data_dir()
    data_dir = Path(data_dir).resolve()
    tree = {}
    for root_d, dirs, files in os.walk(data_dir):
        rel = Path(root_d).relative_to(data_dir).as_posix()
        if rel == ".":
            rel = ""
        matched_files = []
        for f in sorted(files):
            rel_f = f"{rel}/{f}" if rel else f
            if files_subset is None or rel_f in files_subset:
                matched_files.append(f)
        tree[rel] = {"dirs": sorted(dirs), "files": matched_files}
    if files_subset is not None:
        needed_dirs = set()
        for rel_f in files_subset:
            parts = rel_f.split("/")[:-1]
            cur = ""
            for p in parts:
                cur = f"{cur}/{p}" if cur else p
                needed_dirs.add(cur)
        clean_tree = {}
        for d, content in tree.items():
            if d == "" or d in needed_dirs or content["files"]:
                filtered_subdirs = [sub for sub in content["dirs"] if (f"{d}/{sub}" if d else sub) in needed_dirs]
                clean_tree[d] = {"dirs": filtered_subdirs, "files": content["files"]}
        return clean_tree, data_dir
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


def build_fat12(out_path="fat12.img", data_dir=None, files_subset=None):
    tree, data_dir = get_data_tree(data_dir, files_subset=files_subset)
    total_size = 20 * 1024 * 1024
    bps = 512
    spc = 16
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
    decoy_data = b"# CORRUPTED_DECOY_PYTHON_GAP\n" * 100

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
            is_del = rel_f in DELETED_TARGETS or (files_subset is not None and not rel_f.endswith((".png", ".ppt", ".doc")))

            if is_del and num_c > 1:
                seg1_c = max(1, num_c // 2)
                p1_sz = seg1_c * csize
                off1 = (data_lba + (cur_cluster - 2) * spc) * bps
                disk[off1:off1 + min(sz, p1_sz)] = data[:p1_sz]
                gap_c = 4
                gap_off = (data_lba + (cur_cluster + seg1_c - 2) * spc) * bps
                disk[gap_off:gap_off + min(len(decoy_data), gap_c * csize)] = decoy_data[:gap_c * csize]
                c2 = cur_cluster + seg1_c + gap_c
                off2 = (data_lba + (c2 - 2) * spc) * bps
                disk[off2:off2 + len(data[p1_sz:])] = data[p1_sz:]
                cur_cluster = c2 + (num_c - seg1_c) + 2
            else:
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
            is_del = rel_f in DELETED_TARGETS or (files_subset is not None and not rel_f.endswith((".png", ".ppt", ".doc")))
            ent_bytes.extend(make_fat_entry(f, file_clusters[rel_f], file_sizes[rel_f], is_dir=False, deleted=is_del))
        if d == "":
            rdet_off = rdet_lba * bps
            disk[rdet_off:rdet_off + len(ent_bytes)] = ent_bytes
        else:
            c_off = (data_lba + (dir_clusters[d] - 2) * spc) * bps
            disk[c_off:c_off + len(ent_bytes)] = ent_bytes

    if out_path:
        with open(out_path, "wb") as f:
            f.write(disk)
        return out_path
    return disk


def build_fat16(out_path="fat16.img", data_dir=None, files_subset=None):
    tree, data_dir = get_data_tree(data_dir, files_subset=files_subset)
    total_size = 25 * 1024 * 1024
    bps = 512
    spc = 8
    csize = bps * spc
    res = 1
    fats = 2
    entries = 512
    spf = 64
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
    struct.pack_into("<I", disk, 0x20, total_size // bps)
    struct.pack_into("<H", disk, 0x16, spf)
    disk[0x36:0x3E] = b"FAT16   "

    fat1_off = res * bps
    fat2_off = (res + spf) * bps

    def set_fat16(c, val):
        for fo in (fat1_off, fat2_off):
            struct.pack_into("<H", disk, fo + c * 2, val & 0xFFFF)

    set_fat16(0, 0xFFF8)
    set_fat16(1, 0xFFFF)

    cur_cluster = 2
    dir_clusters = {}
    for d in sorted(tree.keys()):
        if d != "":
            dir_clusters[d] = cur_cluster
            set_fat16(cur_cluster, 0xFFFF)
            cur_cluster += 1

    file_clusters = {}
    file_sizes = {}
    interleave_a = "srcs/c/tests.c"
    interleave_b = "srcs/c/tests.cpp"
    interleave_done = False
    decoy_mark = b"/* CORRUPTED_FAT16_DECOY_BLOCKER */\n" * 50

    for d, content in tree.items():
        for f in content["files"]:
            rel_f = f"{d}/{f}" if d else f
            if rel_f in (interleave_a, interleave_b):
                if not interleave_done:
                    interleave_done = True
                    pa = data_dir / interleave_a
                    pb = data_dir / interleave_b
                    with open(pa, "rb") as fpa:
                        da = fpa.read()
                    with open(pb, "rb") as fpb:
                        db = fpb.read()
                    sza = len(da)
                    szb = len(db)
                    file_sizes[interleave_a] = sza
                    file_sizes[interleave_b] = szb
                    nca = max(1, (sza + csize - 1) // csize)
                    ncb = max(1, (szb + csize - 1) // csize)

                    pos_a = 0
                    pos_b = 0
                    first_a = None
                    first_b = None

                    while pos_a < nca or pos_b < ncb:
                        if pos_a < nca:
                            take_a = min(2, nca - pos_a)
                            if first_a is None:
                                first_a = cur_cluster
                            chunk_a = da[pos_a * csize:(pos_a + take_a) * csize]
                            off_a = (data_lba + (cur_cluster - 2) * spc) * bps
                            disk[off_a:off_a + len(chunk_a)] = chunk_a
                            cur_cluster += take_a
                            pos_a += take_a

                        if pos_b < ncb:
                            take_b = min(2, ncb - pos_b)
                            if first_b is None:
                                first_b = cur_cluster
                            chunk_b = db[pos_b * csize:(pos_b + take_b) * csize]
                            off_b = (data_lba + (cur_cluster - 2) * spc) * bps
                            disk[off_b:off_b + len(chunk_b)] = chunk_b
                            cur_cluster += take_b
                            pos_b += take_b

                    file_clusters[interleave_a] = first_a
                    file_clusters[interleave_b] = first_b
                    cur_cluster += 4
                continue

            abs_p = data_dir / rel_f
            with open(abs_p, "rb") as fp:
                data = fp.read()
            sz = len(data)
            file_sizes[rel_f] = sz
            file_clusters[rel_f] = cur_cluster
            num_c = max(1, (sz + csize - 1) // csize)
            is_del = rel_f in DELETED_TARGETS or (files_subset is not None and not rel_f.endswith((".png", ".ppt", ".doc")))

            if is_del and num_c > 1:
                half_c = max(1, num_c // 2)
                p1_sz = half_c * csize
                off1 = (data_lba + (cur_cluster - 2) * spc) * bps
                disk[off1:off1 + min(sz, p1_sz)] = data[:p1_sz]
                blocker_c = cur_cluster + half_c
                blocker_off = (data_lba + (blocker_c - 2) * spc) * bps
                disk[blocker_off:blocker_off + len(decoy_mark)] = decoy_mark
                c2 = blocker_c + 2
                off2 = (data_lba + (c2 - 2) * spc) * bps
                disk[off2:off2 + len(data[p1_sz:])] = data[p1_sz:]
                cur_cluster = c2 + (num_c - half_c) + 2
            else:
                off = (data_lba + (cur_cluster - 2) * spc) * bps
                disk[off:off + sz] = data
                if not is_del:
                    for i in range(num_c - 1):
                        set_fat16(cur_cluster + i, cur_cluster + i + 1)
                    set_fat16(cur_cluster + num_c - 1, 0xFFFF)
                cur_cluster += num_c

    for d, content in tree.items():
        ent_bytes = bytearray()
        for sub in content["dirs"]:
            sub_rel = f"{d}/{sub}" if d else sub
            ent_bytes.extend(make_fat_entry(sub, dir_clusters[sub_rel], 0, is_dir=True))
        for f in content["files"]:
            rel_f = f"{d}/{f}" if d else f
            is_del = rel_f in DELETED_TARGETS or (files_subset is not None and not rel_f.endswith((".png", ".ppt", ".doc")))
            ent_bytes.extend(make_fat_entry(f, file_clusters[rel_f], file_sizes[rel_f], is_dir=False, deleted=is_del))
        if d == "":
            rdet_off = rdet_lba * bps
            disk[rdet_off:rdet_off + len(ent_bytes)] = ent_bytes
        else:
            c_off = (data_lba + (dir_clusters[d] - 2) * spc) * bps
            disk[c_off:c_off + len(ent_bytes)] = ent_bytes

    if out_path:
        with open(out_path, "wb") as f:
            f.write(disk)
        return out_path
    return disk


def build_fat32(out_path="fat32.img", data_dir=None, files_subset=None):
    tree, data_dir = get_data_tree(data_dir, files_subset=files_subset)
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

    scenario1_files = {"srcs/ts/tests.ts", "srcs/python/tests.py"}
    interleave_a = "srcs/js/tests.js"
    interleave_b = "images/tests.jpg"
    scenario3_files = {"srcs/java/tests.java", "srcs/c/tests.c"}
    blocker_mark = b"CORRUPTED_BLOCKER_DATA_ZEROED\x00"
    interleave_processed = False

    for d, content in tree.items():
        for f in content["files"]:
            rel_f = f"{d}/{f}" if d else f
            abs_p = data_dir / rel_f
            with open(abs_p, "rb") as fp:
                data = fp.read()
            sz = len(data)
            file_sizes[rel_f] = sz
            num_c = max(1, (sz + csize - 1) // csize)
            is_del = rel_f in DELETED_TARGETS or (files_subset is not None and not rel_f.endswith((".png", ".ppt", ".doc")))

            if rel_f in (interleave_a, interleave_b):
                if not interleave_processed:
                    interleave_processed = True
                    pa = data_dir / interleave_a
                    pb = data_dir / interleave_b
                    with open(pa, "rb") as fpa:
                        da = fpa.read()
                    with open(pb, "rb") as fpb:
                        db = fpb.read()
                    sza = len(da)
                    szb = len(db)
                    file_sizes[interleave_a] = sza
                    file_sizes[interleave_b] = szb
                    nca = max(1, (sza + csize - 1) // csize)
                    ncb = max(1, (szb + csize - 1) // csize)

                    pos_a = 0
                    pos_b = 0
                    first_a = None
                    first_b = None

                    while pos_a < nca or pos_b < ncb:
                        if pos_a < nca:
                            take_a = min(2, nca - pos_a)
                            if first_a is None:
                                first_a = cur_cluster
                            chunk_a = da[pos_a * csize:(pos_a + take_a) * csize]
                            off_a = (data_lba + (cur_cluster - 2) * spc) * bps
                            disk[off_a:off_a + len(chunk_a)] = chunk_a
                            cur_cluster += take_a
                            pos_a += take_a

                        if pos_b < ncb:
                            take_b = min(1, ncb - pos_b)
                            if first_b is None:
                                first_b = cur_cluster
                            chunk_b = db[pos_b * csize:(pos_b + take_b) * csize]
                            off_b = (data_lba + (cur_cluster - 2) * spc) * bps
                            disk[off_b:off_b + len(chunk_b)] = chunk_b
                            cur_cluster += take_b
                            pos_b += take_b

                    file_clusters[interleave_a] = first_a
                    file_clusters[interleave_b] = first_b
                    cur_cluster += 4
                continue

            file_clusters[rel_f] = cur_cluster

            if is_del and rel_f in scenario1_files and num_c >= 3:
                seg1_c = max(1, num_c // 3)
                seg2_c = max(1, num_c // 3)
                seg3_c = num_c - seg1_c - seg2_c

                p1_len = seg1_c * csize
                off1 = (data_lba + (cur_cluster - 2) * spc) * bps
                disk[off1:off1 + min(sz, p1_len)] = data[:p1_len]
                cur_cluster += seg1_c + 6

                p2_len = seg2_c * csize
                off2 = (data_lba + (cur_cluster - 2) * spc) * bps
                disk[off2:off2 + min(sz - p1_len, p2_len)] = data[p1_len:p1_len + p2_len]
                cur_cluster += seg2_c + 8

                off3 = (data_lba + (cur_cluster - 2) * spc) * bps
                p3_data = data[p1_len + p2_len:]
                disk[off3:off3 + len(p3_data)] = p3_data
                cur_cluster += seg3_c + 6

            elif is_del and rel_f in scenario3_files and num_c > 1:
                half_c = max(1, num_c // 2)
                p1_sz = half_c * csize
                off1 = (data_lba + (cur_cluster - 2) * spc) * bps
                disk[off1:off1 + min(sz, p1_sz)] = data[:p1_sz]
                blocker_c = cur_cluster + half_c
                blocker_off = (data_lba + (blocker_c - 2) * spc) * bps
                disk[blocker_off:blocker_off + len(blocker_mark)] = blocker_mark
                c2 = blocker_c + 1
                off2 = (data_lba + (c2 - 2) * spc) * bps
                disk[off2:off2 + len(data[p1_sz:])] = data[p1_sz:]
                cur_cluster = c2 + (num_c - half_c) + 4

            elif is_del and num_c > 1:
                half_c = max(1, num_c // 2)
                p1_sz = half_c * csize
                off1 = (data_lba + (cur_cluster - 2) * spc) * bps
                disk[off1:off1 + min(sz, p1_sz)] = data[:p1_sz]
                c2 = cur_cluster + half_c + 4
                off2 = (data_lba + (c2 - 2) * spc) * bps
                disk[off2:off2 + len(data[p1_sz:])] = data[p1_sz:]
                cur_cluster = c2 + (num_c - half_c) + 2

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
            is_del = rel_f in DELETED_TARGETS or (files_subset is not None and not rel_f.endswith((".png", ".ppt", ".doc")))
            ent_bytes.extend(make_fat_entry(f, file_clusters[rel_f], file_sizes[rel_f], is_dir=False, is_fat32=True, deleted=is_del))
        c_off = (data_lba + (dir_clusters[d] - 2) * spc) * bps
        disk[c_off:c_off + len(ent_bytes)] = ent_bytes

    if out_path:
        with open(out_path, "wb") as f:
            f.write(disk)
        return out_path
    return disk


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


def build_ntfs(out_path="ntfs.img", data_dir=None, files_subset=None):
    if data_dir is None:
        data_dir = get_default_data_dir()
    data_dir = Path(data_dir).resolve()
    total_size = 35 * 1024 * 1024
    disk = bytearray(total_size)
    disk[510:512] = b"\x55\xaa"
    disk[3:11] = b"NTFS    "
    struct.pack_into("<H", disk, 0x0B, 512)
    disk[0x0D] = 8
    struct.pack_into("<q", disk, 0x30, 2000)

    bps = 512
    spc = 8
    csize = bps * spc

    if files_subset is not None:
        file_defs = [
            ("tests.docx", data_dir / "docs" / "tests.docx", True, [(80, 50), (80, 160), (91, 280)]),
            ("tests.go", data_dir / "srcs" / "go" / "tests.go", True, [(120, 400), (120, 560), (120, 720), (129, 900)]),
            ("tests.rs", data_dir / "srcs" / "rust" / "tests.rs", True, [(130, 1050), (130, 1220), (140, 1400)]),
            ("tests.xls", data_dir / "tests.xls", True, [(135, 1600), (135, 1780)]),
            ("tests.pptx", data_dir / "tests.pptx", False, [(500, 2500), (500, 3100), (500, 3700), (500, 4300), (418, 4900)]),
            ("tests.cs", data_dir / "srcs" / "c" / "tests.cs", False, [(130, 5500), (130, 5700), (127, 5900)])
        ]
    else:
        file_defs = [
            ("tests.docx", data_dir / "docs" / "tests.docx", True, [(80, 50), (80, 160), (91, 280)]),
            ("tests.pdf", data_dir / "docs" / "tests.pdf", False, [(45, 350)]),
            ("tests.jpg", data_dir / "images" / "tests.jpg", True, [(9, 420)]),
            ("tests.c", data_dir / "srcs" / "c" / "tests.c", True, [(200, 500), (237, 750)])
        ]

    recs = []
    sec_offsets = []
    base_mft_sec = 2000 * spc

    for idx, (fn, fpath, is_del, runs) in enumerate(file_defs):
        if not fpath.exists():
            continue
        with open(fpath, "rb") as fp:
            fdata = fp.read()
        fsz = len(fdata)
        rec = make_ntfs_record(16 + idx, fn, 5, size=fsz, runs=runs, is_dir=False, csize=csize, deleted=is_del)
        recs.append(rec)
        sec_offsets.append((base_mft_sec + idx * 2) * bps)

        pos = 0
        for rlen, lcn in runs:
            chunk_len = min(len(fdata) - pos, rlen * csize)
            if chunk_len <= 0:
                break
            off = lcn * csize
            disk[off:off + chunk_len] = fdata[pos:pos + chunk_len]
            pos += chunk_len

    for r, sec_off in zip(recs, sec_offsets):
        disk[sec_off:sec_off + 1024] = r

    if out_path:
        with open(out_path, "wb") as f:
            f.write(disk)
        return out_path
    return disk


def build_disk(out_path="disk.img", data_dir=None):
    if data_dir is None:
        data_dir = get_default_data_dir()
    data_dir = Path(data_dir).resolve()

    f12_subset = {
        "srcs/python/tests.py",
        "docs/tests.txt",
        "images/tests.png",
        "srcs/c/tests.h",
        "tests.xlsx"
    }
    f16_subset = {
        "srcs/c/tests.c",
        "srcs/c/tests.cpp",
        "docs/tests.pdf",
        "tests.zip",
        "tests.ppt"
    }
    f32_subset = {
        "srcs/ts/tests.ts",
        "srcs/js/tests.js",
        "images/tests.jpg",
        "srcs/java/tests.java",
        "srcs/json/tests.json",
        "docs/tests.doc"
    }
    ntfs_subset = {
        "docs/tests.docx",
        "srcs/go/tests.go",
        "srcs/rust/tests.rs",
        "tests.xls",
        "tests.pptx",
        "srcs/c/tests.cs"
    }

    f12_bytes = build_fat12(None, data_dir, files_subset=f12_subset)
    f16_bytes = build_fat16(None, data_dir, files_subset=f16_subset)
    f32_bytes = build_fat32(None, data_dir, files_subset=f32_subset)
    ntfs_bytes = build_ntfs(None, data_dir, files_subset=ntfs_subset)

    f12_sectors = (len(f12_bytes) + 511) // 512
    f16_sectors = (len(f16_bytes) + 511) // 512
    f32_sectors = (len(f32_bytes) + 511) // 512
    ntfs_sectors = (len(ntfs_bytes) + 511) // 512

    p1_lba = 2048
    p2_lba = ((p1_lba + f12_sectors + 2047) // 2048) * 2048
    p3_lba = ((p2_lba + f16_sectors + 2047) // 2048) * 2048
    p4_lba = ((p3_lba + f32_sectors + 2047) // 2048) * 2048

    total_sectors = p4_lba + ntfs_sectors
    total_size = total_sectors * 512
    disk = bytearray(total_size)

    disk[0:2] = b"\xeb\xfe"
    disk[510:512] = b"\x55\xaa"

    parts_info = [
        (0x1BE, 0x80, 0x01, p1_lba, f12_sectors),
        (0x1CE, 0x00, 0x06, p2_lba, f16_sectors),
        (0x1DE, 0x00, 0x0C, p3_lba, f32_sectors),
        (0x1EE, 0x00, 0x07, p4_lba, ntfs_sectors)
    ]

    for offset, status, ptype, start_lba, num_sec in parts_info:
        disk[offset] = status
        disk[offset + 4] = ptype
        struct.pack_into("<I", disk, offset + 8, start_lba)
        struct.pack_into("<I", disk, offset + 12, num_sec)

    p1_off = p1_lba * 512
    disk[p1_off:p1_off + len(f12_bytes)] = f12_bytes

    p2_off = p2_lba * 512
    disk[p2_off:p2_off + len(f16_bytes)] = f16_bytes

    p3_off = p3_lba * 512
    disk[p3_off:p3_off + len(f32_bytes)] = f32_bytes

    p4_off = p4_lba * 512
    disk[p4_off:p4_off + len(ntfs_bytes)] = ntfs_bytes

    with open(out_path, "wb") as f:
        f.write(disk)
    return out_path


def build_all(data_dir=None):
    f12 = build_fat12("fat12.img", data_dir)
    f16 = build_fat16("fat16.img", data_dir)
    f32 = build_fat32("fat32.img", data_dir)
    ntfs = build_ntfs("ntfs.img", data_dir)
    dsk = build_disk("disk.img", data_dir)
    return [f12, f16, f32, ntfs, dsk]


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
            self.assertEqual(info.get("fs"), "FAT16")
            items = router.scan(d, info)
            self.assertTrue(len(items) >= 4)

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

    def test_build_and_detect_disk(self):
        p = "disk.img"
        build_disk(p)
        self.assertTrue(os.path.exists(p))
        with disk_read.Disk(p) as d:
            parts = parse_mod.scan(d)
            self.assertEqual(len(parts), 4)
            fs_list = [p["fs"] for p in parts]
            self.assertEqual(fs_list, ["FAT12", "FAT16", "FAT32", "NTFS"])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("build", "--build"):
        paths = build_all()
        for p in paths:
            print(f"Generated: {p} ({os.path.getsize(p)} bytes)")
    else:
        unittest.main(verbosity=2)
