import struct
import io
import importlib

file_valid = importlib.import_module("tools.file-valid")


def calc_png_size(raw, start=0):
    pos = start + 8
    max_bound = min(len(raw), start + 50 * 1024 * 1024)
    while pos + 8 <= max_bound:
        length = struct.unpack(">I", raw[pos:pos + 4])[0]
        chunk_type = raw[pos + 4:pos + 8]
        pos += 8 + length + 4
        if chunk_type == b"IEND":
            return pos - start
    return None


def calc_jpg_size(raw, start=0):
    max_bound = min(len(raw), start + 50 * 1024 * 1024)
    idx = raw.find(b"\xFF\xD9", start + 4)
    if idx != -1 and idx <= max_bound:
        return (idx + 2) - start
    return None


def calc_zip_size(raw, start=0):
    max_bound = min(len(raw), start + 100 * 1024 * 1024)
    eocd = raw.find(b"PK\x05\x06", start, max_bound)
    if eocd == -1 or eocd + 22 > len(raw):
        return None, None
    comment_len = struct.unpack_from("<H", raw, eocd + 20)[0]
    total_len = (eocd + 22 + comment_len) - start
    sniff = raw[start:eocd + 22]
    ext = "zip"
    if b"word/document.xml" in sniff or b"word/" in sniff and b"ppt/presentation.xml" not in sniff and b"xl/workbook.xml" not in sniff:
        ext = "docx"
    elif b"ppt/presentation.xml" in sniff:
        ext = "pptx"
    elif b"xl/workbook.xml" in sniff:
        ext = "xlsx"
    elif b"ppt/" in sniff:
        ext = "pptx"
    elif b"xl/" in sniff:
        ext = "xlsx"
    return total_len, ext


def calc_ole_size(raw, start=0):
    if len(raw) < start + 512:
        return None, None
    sector_shift = struct.unpack_from("<H", raw, start + 0x1E)[0]
    if sector_shift not in (9, 12):
        return None, None
    sector_size = 1 << sector_shift
    fat_sectors = struct.unpack_from("<I", raw, start + 0x2C)[0]
    difat = list(struct.unpack_from("<109I", raw, start + 0x4C))
    max_sec = -1
    for i in range(min(fat_sectors, 109)):
        fat_sec = difat[i]
        if fat_sec >= 0xFFFFFFFC:
            continue
        off = start + (fat_sec + 1) * sector_size
        if off + sector_size > len(raw):
            break
        entries = struct.unpack_from(f"<{sector_size // 4}I", raw, off)
        for idx, val in enumerate(entries):
            if val != 0xFFFFFFFF:
                sec_num = i * (sector_size // 4) + idx
                if sec_num > max_sec:
                    max_sec = sec_num
    sniff = raw[start:start + min(len(raw) - start, 65536)]
    ext = "doc"
    if b"W\x00o\x00r\x00k\x00b\x00o\x00o\x00k" in sniff or b"B\x00o\x00o\x00k" in sniff:
        ext = "xls"
    elif b"P\x00o\x00w\x00e\x00r\x00P\x00o\x00i\x00n\x00t" in sniff:
        ext = "ppt"
    elif b"W\x00o\x00r\x00d\x00D\x00o\x00c" in sniff:
        ext = "doc"
    if max_sec >= 0:
        size = (max_sec + 2) * sector_size
    else:
        size = max(sector_size * 2, (1 + fat_sectors) * sector_size)
    return size, ext


def calc_pdf_size(raw, start=0):
    max_bound = min(len(raw), start + 100 * 1024 * 1024)
    idx = raw.find(b"%%EOF", start, max_bound)
    if idx != -1:
        end = idx + 5
        while end < len(raw) and raw[end:end + 1] in (b"\r", b"\n"):
            end += 1
        return end - start
    return None


def classify_text_ext(text):
    head = text[:2048]
    s = head.lstrip()
    if s.startswith("{") or s.startswith("["):
        ok, _ = file_valid.validate(text.encode("utf-8", errors="ignore"), "json")
        if ok:
            return "json"
    if "package main" in head or ("func " in head and "struct {" in head):
        return "go"
    if "impl " in head and "fn " in head:
        return "rs"
    if "public class " in head and ("package " in head or "System." in head):
        return "java"
    if "using System;" in head or ("namespace " in head and "public class " in head):
        return "cs"
    if "def " in head and ("import " in head or "from " in head):
        return "py"
    if ("interface " in head or "export function " in head) and any(t in head for t in (": number", ": string", ": boolean")):
        return "ts"
    if ("const " in head or "function " in head or "require(" in head) and "=>" in text[:4096] or "require(" in head:
        return "js"
    if "#include <iostream>" in head or "namespace " in head or "std::" in head or "class " in head:
        return "cpp"
    if "#ifndef " in head and "#define " in head:
        return "h"
    if "#include " in head and ("int " in head or "void " in head or "struct " in head):
        return "c"
    return "txt"


def carve_disk(disk, chunk_size=1048576, max_files=100):
    total_size = disk.size()
    files = []
    seen_offsets = set()
    carved_ranges = []
    pos = 0
    idx = 1

    sigs = [
        (b"\x89PNG\r\n\x1a\n", "png"),
        (b"\xFF\xD8\xFF", "jpg"),
        (b"PK\x03\x04", "zip"),
        (b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1", "ole"),
        (b"%PDF-", "pdf")
    ]

    while pos < total_size and len(files) < max_files:
        containing = [e for s, e in carved_ranges if s <= pos < e]
        if containing:
            pos = max(containing)
            continue

        chunk = disk.read(pos, chunk_size + 16384)
        if not chunk or len(chunk) < 512:
            break

        cursor = 0
        while cursor < min(len(chunk), chunk_size) and len(files) < max_files:
            best_hit = -1
            best_sig = None
            for sig_bytes, sig_type in sigs:
                h = chunk.find(sig_bytes, cursor)
                if h != -1 and (best_hit == -1 or h < best_hit):
                    best_hit = h
                    best_sig = sig_type

            if best_hit == -1 or best_hit >= chunk_size:
                break

            abs_offset = pos + best_hit
            if abs_offset in seen_offsets or any(s <= abs_offset < e for s, e in carved_ranges):
                cursor = best_hit + 4
                continue

            remaining = chunk[best_hit:]

            def compute_size(buf, stype):
                if stype == "png":
                    return calc_png_size(buf, 0), "png"
                elif stype == "jpg":
                    return calc_jpg_size(buf, 0), "jpg"
                elif stype == "zip":
                    return calc_zip_size(buf, 0)
                elif stype == "ole":
                    return calc_ole_size(buf, 0)
                elif stype == "pdf":
                    return calc_pdf_size(buf, 0), "pdf"
                return None, stype

            size, ext = compute_size(remaining, best_sig)
            if not size and abs_offset < total_size:
                big_buf = disk.read(abs_offset, min(16 * 1024 * 1024, total_size - abs_offset))
                size, ext = compute_size(big_buf, best_sig)

            if size and size > 0 and abs_offset + size <= total_size:
                payload = disk.read(abs_offset, size)
                ok, _ = file_valid.validate(payload, ext)
                if ok:
                    seen_offsets.add(abs_offset)
                    carved_ranges.append((abs_offset, abs_offset + size))
                    filename = f"carved_{idx}.{ext}"
                    cluster_id = abs_offset // 4096
                    files.append({
                        "name": filename,
                        "path": f"/{filename}",
                        "cluster": cluster_id,
                        "size": len(payload),
                        "deleted": True,
                        "is_dir": False,
                        "lang": ext,
                        "offset": abs_offset,
                        "carved": True,
                        "payload": payload
                    })
                    idx += 1
                    cursor = best_hit + size
                    continue

            cursor = best_hit + 4

        pos += chunk_size

    # Second pass: carve contiguous plain-text/code blocks outside binary ranges
    cluster_sz = 4096
    c_off = 0
    while c_off < total_size and len(files) < max_files:
        if any(s <= c_off < e for s, e in carved_ranges):
            c_off += cluster_sz
            continue
        head = disk.read(c_off, min(cluster_sz, total_size - c_off))
        if not head or not any(head):
            c_off += cluster_sz
            continue
        stripped_head = head.rstrip(b"\x00")
        if len(stripped_head) >= 64:
            non_ascii = sum(1 for b in stripped_head if b > 126 or (b < 32 and b not in (9, 10, 13)))
            if non_ascii == 0:
                start_off = c_off
                parts = []
                cur_off = c_off
                while cur_off < total_size:
                    if any(s <= cur_off < e for s, e in carved_ranges):
                        break
                    blk = disk.read(cur_off, min(cluster_sz, total_size - cur_off))
                    if not blk or not any(blk):
                        break
                    s_blk = blk.rstrip(b"\x00")
                    if any(b > 126 or (b < 32 and b not in (9, 10, 13)) for b in s_blk):
                        break
                    parts.append(blk)
                    cur_off += cluster_sz
                    if len(s_blk) < len(blk):
                        break
                if parts:
                    raw_payload = b"".join(parts).rstrip(b"\x00")
                    if len(raw_payload) >= 128:
                        text_str = raw_payload.decode("utf-8", errors="ignore")
                        ext = classify_text_ext(text_str)
                        ok, _ = file_valid.validate(raw_payload, ext)
                        if ok:
                            carved_ranges.append((start_off, cur_off))
                            filename = f"carved_{idx}.{ext}"
                            files.append({
                                "name": filename,
                                "path": f"/{filename}",
                                "cluster": start_off // cluster_sz,
                                "size": len(raw_payload),
                                "deleted": True,
                                "is_dir": False,
                                "lang": ext,
                                "offset": start_off,
                                "carved": True,
                                "payload": raw_payload
                            })
                            idx += 1
                            c_off = cur_off
                            continue
        c_off += cluster_sz

    return files
