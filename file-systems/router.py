import importlib

fat_info = importlib.import_module("file-systems.fat.fat-info")
fat32_info = importlib.import_module("file-systems.fat.fat32-info")
ntfs_info = importlib.import_module("file-systems.ntfs.ntfs-info")
carver = importlib.import_module("utils.carver")


def scan(disk, info):
    fs = info.get("fs", "")
    items = []
    if fs == "NTFS":
        items = ntfs_info.scan(disk, info)
    elif fs == "FAT32":
        items = fat32_info.scan(disk, info)
    elif fs in ("FAT16", "FAT12"):
        items = fat_info.scan(disk, info)
    if not items:
        items = carver.carve_disk(disk)
    return items
