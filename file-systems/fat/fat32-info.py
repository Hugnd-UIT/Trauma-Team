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
    ".json": "json"
}


def decode_lfn(entry):
    parts = []
    # 5 chars at 0x01
    parts.append(entry[1:11])
    # 6 chars at 0x0E
    parts.append(entry[14:26])
    # 2 chars at 0x1C
    parts.append(entry[28:32])
    raw = b"".join(parts)
    text = raw.decode("utf-16le", errors="ignore")
    return text.split("\x00")[0]


def scan(disk, info):
    files = []
    spc = info.get("spc", 8)
    bps = info.get("bps", 512)
    data_lba = info.get("data_lba", 0)
    res = info.get("res", 32)
    root = info.get("root", 2)
    fat_offset = res * bps

    max_clusters = (disk.size() - data_lba * bps) // (spc * bps) + 2
    queue = [(root, "/")]
    visited_dirs = set()

    while queue:
        dir_start, parent = queue.pop(0)
        if dir_start in visited_dirs or dir_start < 2 or dir_start >= max_clusters:
            continue
        visited_dirs.add(dir_start)

        # Follow directory cluster chain via FAT table
        dir_clusters = []
        cur = dir_start
        while 2 <= cur < max_clusters and cur not in dir_clusters:
            dir_clusters.append(cur)
            fat_entry_offset = fat_offset + cur * 4
            if fat_entry_offset + 4 > disk.size():
                break
            next_clus = struct.unpack_from("<I", disk.read(fat_entry_offset, 4))[0] & 0x0FFFFFFF
            if next_clus >= 0x0FFFFFF8 or next_clus < 2:
                break
            cur = next_clus

        # Read all clusters belonging to this directory
        raw = b"".join(disk.cluster(c, data_lba, spc, bps) for c in dir_clusters)
        if not raw:
            continue

        lfn_parts = []
        for i in range(0, len(raw), 32):
            entry = raw[i:i + 32]
            if len(entry) < 32:
                break

            b0 = entry[0]
            if b0 == 0x00:
                break

            attr = entry[0x0B]
            if attr != 0x0F and (attr & ~0x3F) != 0:
                continue

            # Decode long filename LFN directory record
            if attr == 0x0F:
                part = decode_lfn(entry)
                lfn_parts.append(part)
                continue

            # Skip volume label attribute entry
            if attr & 0x08:
                lfn_parts = []
                continue

            deleted = (b0 == 0xE5)
            is_dir = bool(attr & 0x10)

            # Name decoding
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

            # Extract starting cluster address and file byte length
            hi = struct.unpack_from("<H", entry, 0x14)[0]
            lo = struct.unpack_from("<H", entry, 0x1A)[0]
            start = (hi << 16) | lo
            size = struct.unpack_from("<I", entry, 0x1C)[0]

            path = f"{parent.rstrip('/')}/{name}"

            # Language check
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

            if is_dir and start >= 2:
                queue.append((start, path))

    return files
