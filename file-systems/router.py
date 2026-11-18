import importlib

fat_info = importlib.import_module("file-systems.fat.fat-info")
fat32_info = importlib.import_module("file-systems.fat.fat32-info")
ntfs_info = importlib.import_module("file-systems.ntfs.ntfs-info")


def scan(disk, info):
    fs = info.get("fs", "")
    if fs == "NTFS":
        return ntfs_info.scan(disk, info)
    elif fs == "FAT32":
        return fat32_info.scan(disk, info)
    elif fs in ("FAT16", "FAT12"):
        return fat_info.scan(disk, info)
    return []
