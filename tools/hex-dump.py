import os
import sys
import struct


def dump(vhd_path="tests/tests.vhd", img_path="test.img"):
    if not os.path.exists(vhd_path):
        print(f"[!] VHD not found: {vhd_path}")
        return False

    print(f"[*] Dumping VHD: {vhd_path} -> {img_path} ...")
    with open(vhd_path, "rb") as fin:
        mbr = fin.read(512)
        start_lba = struct.unpack_from("<I", mbr, 0x1BE + 8)[0]
        num_sec = struct.unpack_from("<I", mbr, 0x1BE + 12)[0]

        if start_lba > 0 and num_sec > 0:
            total_bytes = num_sec * 512
            fin.seek(start_lba * 512)
            print(f"[+] Found Partition 1: Start LBA={start_lba}, Size={total_bytes} bytes (~{total_bytes / (1024 * 1024):.1f} MB)")
        else:
            total_bytes = os.path.getsize(vhd_path) - 512
            fin.seek(0)
            print(f"[+] Raw VHD Image Size: {total_bytes} bytes")

        with open(img_path, "wb") as fout:
            left = total_bytes
            while left > 0:
                chunk = fin.read(min(left, 1048576))
                if not chunk:
                    break
                fout.write(chunk)
                left -= len(chunk)

    print(f"[+] Successfully exported {img_path} ({os.path.getsize(img_path)} bytes)!")
    return True


if __name__ == "__main__":
    vhd = sys.argv[1] if len(sys.argv) > 1 else "tests/tests.vhd"
    img = sys.argv[2] if len(sys.argv) > 2 else "test.img"
    dump(vhd, img)
