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
    eocd = raw.rfind(b"PK\x05\x06", start, max_bound)
    if eocd == -1:
        return None, None
    comment_len = struct.unpack_from("<H", raw, eocd + 20)[0]
    total_len = (eocd + 22 + comment_len) - start
    sniff = raw[start:eocd + 22]
    ext = "zip"
    if b"word/" in sniff:
        ext = "docx"
    elif b"xl/" in sniff:
        ext = "xlsx"
    elif b"ppt/" in sniff:
        ext = "pptx"
    return total_len, ext


def calc_ole_size(raw, start=0):
    if len(raw) < start + 512:
        return None, None
    sector_shift = struct.unpack_from("<H", raw, start + 0x1E)[0]
    if sector_shift not in (9, 12):
        return None, None
    sector_size = 1 << sector_shift
    fat_sectors = struct.unpack_from("<I", raw, start + 0x2C)[0]
    sniff = raw[start:start + 65536]
    ext = "doc"
    if b"W\x00o\x00r\x00k\x00b\x00o\x00o\x00k" in sniff or b"B\x00o\x00o\x00k" in sniff:
        ext = "xls"
    elif b"P\x00o\x00w\x00e\x00r\x00P\x00o\x00i\x00n\x00t" in sniff:
        ext = "ppt"
    elif b"W\x00o\x00r\x00d\x00D\x00o\x00c" in sniff:
        ext = "doc"
    size = max(sector_size * 2, (1 + fat_sectors) * sector_size)
    return size, ext


def calc_pdf_size(raw, start=0):
    max_bound = min(len(raw), start + 100 * 1024 * 1024)
    idx = raw.rfind(b"%%EOF", start, max_bound)
    if idx != -1:
        end = idx + 5
        while end < len(raw) and raw[end:end + 1] in (b"\r", b"\n"):
            end += 1
        return end - start
    return None


def carve_disk(disk, chunk_size=1048576, max_files=100):
    total_size = disk.size()
    files = []
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
        chunk = disk.read(pos, chunk_size + 16384)
        if not chunk or len(chunk) < 512:
            break

        for sig_bytes, sig_type in sigs:
            offset_in_chunk = 0
            while True:
                hit = chunk.find(sig_bytes, offset_in_chunk)
                if hit == -1:
                    break

                abs_offset = pos + hit
                remaining = chunk[hit:]
                size = None
                ext = sig_type

                if sig_type == "png":
                    size = calc_png_size(remaining, 0)
                elif sig_type == "jpg":
                    size = calc_jpg_size(remaining, 0)
                elif sig_type == "zip":
                    size, ext = calc_zip_size(remaining, 0)
                elif sig_type == "ole":
                    size, ext = calc_ole_size(remaining, 0)
                elif sig_type == "pdf":
                    size = calc_pdf_size(remaining, 0)

                if size and size > 0:
                    payload = disk.read(abs_offset, size)
                    ok, _ = file_valid.validate(payload, ext)
                    if ok:
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
                        offset_in_chunk = hit + size
                        continue

                offset_in_chunk = hit + 4

        pos += chunk_size

    return files
