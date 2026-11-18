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


def decode_lfn(entry):
    parts = []
    parts.append(entry[1:11])
    parts.append(entry[14:26])
    parts.append(entry[28:32])
    raw = b"".join(parts)
    text = raw.decode("utf-16le", errors="ignore")
    return text.split("\x00")[0]


def scan(disk, info):
    files = []
    spc = info.get("spc", 4)
    bps = info.get("bps", 512)
    data_lba = info.get("data_lba", 0)
    rdet_lba = info.get("rdet_lba", 0)
    entries = info.get("entries", 512)

    # Read Root Directory at dedicated LBA for FAT12 and FAT16
    rdet_size = entries * 32
    rdet_raw = disk.read(rdet_lba * bps, rdet_size)

    queue = [(rdet_raw, "/", True)]
    seen_clusters = set()
    max_clusters = (disk.size() // bps - data_lba) // spc + 2

    while queue:
        raw, parent, is_root = queue.pop(0)
        lfn_parts = []

        for i in range(0, len(raw), 32):
            entry = raw[i:i + 32]
            if len(entry) < 32:
                break

            b0 = entry[0]
            if b0 == 0x00:
                break

            attr = entry[0x0B]
            if attr == 0x0F:
                lfn_parts.append(decode_lfn(entry))
                continue

            if attr & 0x08:
                lfn_parts = []
                continue

            deleted = (b0 == 0xE5)
            is_dir = bool(attr & 0x10)

            if lfn_parts:
                name = "".join(reversed(lfn_parts)).strip()
                lfn_parts = []
            else:
                base = entry[:8].decode("ascii", errors="ignore").strip()
                ext = entry[8:11].decode("ascii", errors="ignore").strip()
                if deleted and base:
                    base = "_" + base[1:]
                name = f"{base}.{ext}" if ext else base

            if name in (".", "..") or not name:
                continue

            # In FAT12 and FAT16 starting cluster is only in offset 0x1A as low word
            start = struct.unpack_from("<H", entry, 0x1A)[0]
            size = struct.unpack_from("<I", entry, 0x1C)[0]

            path = f"{parent.rstrip('/')}/{name}"
            ext_lower = "." + name.split(".")[-1].lower() if "." in name else ""
            lang = CODE_EXTS.get(ext_lower, "")

            item = {
                "name": name,
                "path": path,
                "parent": parent,
                "cluster": start,
                "size": size,
                "deleted": deleted,
                "is_dir": is_dir,
                "lang": lang
            }
            files.append(item)

            if is_dir and start >= 2 and start < max_clusters and start not in seen_clusters:
                seen_clusters.add(start)
                sub_raw = disk.cluster(start, data_lba, spc, bps)
                if sub_raw:
                    queue.append((sub_raw, path, False))

    return files
