import struct

CODE_EXTS = {
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "cs",
    ".py": "py",
    ".h": "c",
    ".rs": "rs",
    ".go": "go",
    ".js": "js",
    ".ts": "ts",
    ".java": "java",
    ".json": "json",
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".doc": "doc",
    ".xls": "xls",
    ".ppt": "ppt",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".pptx": "pptx",
    ".pdf": "pdf",
    ".zip": "zip"
}


def decode_runs(raw, start_pos, end_pos):
    runs = []
    pos = start_pos
    cur_lcn = 0

    while pos < end_pos:
        b = raw[pos]
        if b == 0:
            break
        len_size = b & 0x0F
        off_size = (b >> 4) & 0x0F
        pos += 1

        rlen = int.from_bytes(raw[pos:pos + len_size], "little", signed=False)
        pos += len_size

        rofs = int.from_bytes(raw[pos:pos + off_size], "little", signed=True)
        pos += off_size

        cur_lcn += rofs
        runs.append((rlen, cur_lcn))

    return runs


def parse_record(rec, idx=0):
    if len(rec) < 1024 or rec[:4] != b"FILE":
        return None

    flags = struct.unpack_from("<H", rec, 0x16)[0]
    deleted = not bool(flags & 0x01)
    is_dir = bool(flags & 0x02)

    first_attr = struct.unpack_from("<H", rec, 0x14)[0]
    pos = first_attr

    name = ""
    parent_id = 5
    size = 0
    resident_data = None
    runs = []

    while pos < len(rec) - 8:
        atype, alen = struct.unpack_from("<II", rec, pos)
        if atype == 0xFFFFFFFF or alen == 0:
            break

        # File name record attribute 0x30
        if atype == 0x30:
            c_off = struct.unpack_from("<H", rec, pos + 0x14)[0]
            content = rec[pos + c_off:pos + alen]
            if len(content) >= 0x42:
                p_id = int.from_bytes(content[0:6], "little")
                fn_len = content[0x40]
                ns = content[0x41]
                fn = content[0x42:0x42 + fn_len * 2].decode("utf-16le", errors="ignore")
                # Prefer Win32 namespace over DOS 8.3 short name
                if ns != 2 or not name:
                    name = fn
                    parent_id = p_id

        # Data attribute 0x80 holding resident or non-resident streams
        elif atype == 0x80:
            non_res = rec[pos + 8]
            if non_res == 0:
                dlen = struct.unpack_from("<I", rec, pos + 0x10)[0]
                doff = struct.unpack_from("<H", rec, pos + 0x14)[0]
                size = dlen
                resident_data = rec[pos + doff:pos + doff + dlen]
            else:
                size = struct.unpack_from("<Q", rec, pos + 0x30)[0]
                runs_off = struct.unpack_from("<H", rec, pos + 0x20)[0]
                runs = decode_runs(rec, pos + runs_off, pos + alen)

        pos += alen

    if not name or name == ".":
        return None

    ext_lower = "." + name.split(".")[-1].lower() if "." in name else ""
    lang = CODE_EXTS.get(ext_lower, "")
    first_cluster = runs[0][1] if runs else 0

    return {
        "id": idx,
        "name": name,
        "parent_id": parent_id,
        "size": size,
        "deleted": deleted,
        "is_dir": is_dir,
        "lang": lang,
        "resident": resident_data is not None,
        "resident_data": resident_data,
        "cluster": first_cluster,
        "runs": runs
    }


def carve_orphaned(disk, info=None, chunk_size=1048576, max_records=2000):
    total_size = disk.size()
    files = []
    seen_names = set()
    pos = 0
    rec_id = 10000

    while pos < total_size and len(files) < max_records:
        chunk = disk.read(pos, chunk_size + 1024)
        if not chunk or len(chunk) < 1024:
            break

        idx = 0
        while True:
            idx = chunk.find(b"FILE", idx)
            if idx == -1 or idx + 1024 > len(chunk):
                break

            # MFT records are aligned to 512 byte sector boundaries
            rec_offset = pos + idx
            if rec_offset % 512 == 0:
                rec_bytes = chunk[idx:idx + 1024]
                item = parse_record(rec_bytes, rec_id)
                if item and item["name"] not in seen_names:
                    seen_names.add(item["name"])
                    item["offset"] = rec_offset
                    item["path"] = "/" + item["name"]
                    files.append(item)
                    rec_id += 1
            idx += 4

        pos += chunk_size

    return files


def scan(disk, info, max_records=None):
    files = []
    mft_lba = info.get("mft_lba", 0)
    bps = info.get("bps", 512)
    mft_offset = mft_lba * bps

    # Calculate upper bound of MFT records based on disk capacity
    if max_records is None:
        max_records = max(0, (disk.size() - mft_offset) // 1024)

    nodes = {}
    consecutive_empty = 0

    if mft_offset < disk.size() and max_records > 0:
        for idx in range(max_records):
            rec_offset = mft_offset + idx * 1024
            if rec_offset >= disk.size():
                break

            rec = disk.read(rec_offset, 1024)
            if len(rec) < 1024 or rec[:4] != b"FILE":
                consecutive_empty += 1
                if consecutive_empty > 512:
                    break
                continue

            consecutive_empty = 0
            item = parse_record(rec, idx)
            if item:
                nodes[idx] = item
                files.append(item)

    # Check MFT Mirror if primary table was empty
    if not files and "mftmirr_lba" in info:
        mirr_offset = info["mftmirr_lba"] * bps
        if mirr_offset < disk.size():
            for idx in range(32):
                rec_offset = mirr_offset + idx * 1024
                if rec_offset >= disk.size():
                    break
                rec = disk.read(rec_offset, 1024)
                if len(rec) < 1024 or rec[:4] != b"FILE":
                    continue
                item = parse_record(rec, idx)
                if item:
                    nodes[idx] = item
                    files.append(item)

    # Fallback to carving orphaned records across disk if MFT is missing
    if not files:
        return carve_orphaned(disk, info)

    # Build full paths based on parent_id hierarchy
    for item in files:
        path_parts = [item["name"]]
        cur_pid = item["parent_id"]
        depth = 0
        while cur_pid in nodes and cur_pid != 5 and depth < 20:
            p_node = nodes[cur_pid]
            path_parts.append(p_node["name"])
            cur_pid = p_node["parent_id"]
            depth += 1
        item["path"] = "/" + "/".join(reversed(path_parts))

    return files
