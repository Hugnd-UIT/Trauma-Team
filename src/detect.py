import struct


def parse(raw):
    if len(raw) < 512:
        return {"fs": "UNKNOWN", "error": "Sector too small"}

    sig = raw[510:512]
    if sig != b"\x55\xaa":
        return {"fs": "UNKNOWN", "error": "Invalid boot signature"}

    oem = raw[3:11].decode("ascii", errors="ignore").strip()
    bps = struct.unpack_from("<H", raw, 0x0B)[0] or 512
    spc = raw[0x0D] or 8
    csize = bps * spc

    # Check NTFS
    if "NTFS" in oem:
        mft_cluster = struct.unpack_from("<q", raw, 0x30)[0]
        return {
            "fs": "NTFS",
            "oem": oem,
            "bps": bps,
            "spc": spc,
            "csize": csize,
            "mft_cluster": mft_cluster,
            "mft_lba": mft_cluster * spc
        }

    # Check FAT32
    f32_sig = raw[0x52:0x5A].decode("ascii", errors="ignore").strip()
    if "FAT32" in f32_sig or "FAT32" in oem:
        res = struct.unpack_from("<H", raw, 0x0E)[0]
        fats = raw[0x10]
        spf = struct.unpack_from("<I", raw, 0x24)[0]
        root = struct.unpack_from("<I", raw, 0x2C)[0] or 2
        data_lba = res + (fats * spf)
        return {
            "fs": "FAT32",
            "oem": oem,
            "bps": bps,
            "spc": spc,
            "csize": csize,
            "res": res,
            "fats": fats,
            "spf": spf,
            "root": root,
            "data_lba": data_lba
        }

    # Check FAT12 / FAT16
    f16_sig = raw[0x36:0x3E].decode("ascii", errors="ignore").strip()
    if "FAT16" in f16_sig or "FAT12" in f16_sig or "FAT" in oem:
        res = struct.unpack_from("<H", raw, 0x0E)[0]
        fats = raw[0x10]
        entries = struct.unpack_from("<H", raw, 0x11)[0]
        spf = struct.unpack_from("<H", raw, 0x16)[0]
        rdet_lba = res + (fats * spf)
        rdet_sec = (entries * 32 + bps - 1) // bps
        data_lba = rdet_lba + rdet_sec
        fs_type = "FAT12" if "FAT12" in f16_sig else "FAT16"
        return {
            "fs": fs_type,
            "oem": oem,
            "bps": bps,
            "spc": spc,
            "csize": csize,
            "res": res,
            "fats": fats,
            "entries": entries,
            "spf": spf,
            "rdet_lba": rdet_lba,
            "data_lba": data_lba
        }

    return {"fs": "UNKNOWN", "oem": oem}


def detect(disk):
    raw = disk.sector(0)
    return parse(raw)
