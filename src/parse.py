import struct
import importlib

detect = importlib.import_module("src.detect")

MBR_TYPES = {
    0x01: "FAT12",
    0x04: "FAT16",
    0x06: "FAT16",
    0x0E: "FAT16",
    0x0B: "FAT32",
    0x0C: "FAT32",
    0x07: "NTFS"
}


def parse_mbr(raw):
    if len(raw) < 512 or raw[510:512] != b"\x55\xaa":
        return []
    parts = []
    for i in range(4):
        entry = raw[0x1BE + i * 16:0x1CE + i * 16]
        status = entry[0]
        type_byte = entry[4]
        if status not in (0x00, 0x80):
            return []
        if type_byte == 0:
            continue
        start_lba = struct.unpack_from("<I", entry, 8)[0]
        sectors = struct.unpack_from("<I", entry, 12)[0]
        if start_lba == 0 or sectors == 0:
            continue
        parts.append({
            "index": i + 1,
            "status": status,
            "type_byte": type_byte,
            "start_lba": start_lba,
            "sectors": sectors,
            "scheme": "MBR"
        })
    return parts


def parse_gpt(disk):
    gpt_head = disk.read(512, 512)
    if len(gpt_head) < 512 or gpt_head[:8] != b"EFI PART":
        return []
    part_lba = struct.unpack_from("<Q", gpt_head, 0x48)[0]
    num_entries = struct.unpack_from("<I", gpt_head, 0x50)[0]
    entry_size = struct.unpack_from("<I", gpt_head, 0x54)[0]
    if entry_size < 128 or num_entries == 0:
        return []

    parts = []
    idx = 1
    for i in range(min(num_entries, 128)):
        entry_raw = disk.read(part_lba * 512 + i * entry_size, entry_size)
        if len(entry_raw) < 128:
            break
        type_guid = entry_raw[:16]
        if type_guid == b"\x00" * 16:
            continue
        start_lba = struct.unpack_from("<Q", entry_raw, 0x20)[0]
        end_lba = struct.unpack_from("<Q", entry_raw, 0x28)[0]
        if end_lba < start_lba:
            continue
        sectors = end_lba - start_lba + 1
        name = entry_raw[0x38:0x80].decode("utf-16le", errors="ignore").split("\x00")[0].strip()
        parts.append({
            "index": idx,
            "name": name,
            "type_guid": type_guid.hex(),
            "start_lba": start_lba,
            "sectors": sectors,
            "scheme": "GPT"
        })
        idx += 1
    return parts


def scan(disk):
    disk.set_partition(0)
    sec0 = disk.sector(0)

    gpt_parts = parse_gpt(disk)
    if gpt_parts:
        for p in gpt_parts:
            p_sec = disk.read(p["start_lba"] * 512, 512)
            p_fs = detect.parse(p_sec).get("fs", "UNKNOWN")
            p["fs"] = p_fs
        return gpt_parts

    mbr_parts = parse_mbr(sec0)
    if mbr_parts:
        for p in mbr_parts:
            p_sec = disk.read(p["start_lba"] * 512, 512)
            p_fs = detect.parse(p_sec).get("fs", "UNKNOWN")
            if p_fs == "UNKNOWN" and p["type_byte"] in MBR_TYPES:
                p_fs = MBR_TYPES[p["type_byte"]]
            p["fs"] = p_fs
        return mbr_parts

    raw_vbr = detect.parse(sec0)
    if raw_vbr.get("fs") != "UNKNOWN":
        return [{
            "index": 1,
            "name": "Volume 1",
            "start_lba": 0,
            "sectors": disk.size() // 512,
            "fs": raw_vbr.get("fs"),
            "scheme": "RAW"
        }]

    return [{
        "index": 1,
        "name": "Volume 1",
        "start_lba": 0,
        "sectors": disk.size() // 512,
        "fs": "UNKNOWN",
        "scheme": "RAW"
    }]
