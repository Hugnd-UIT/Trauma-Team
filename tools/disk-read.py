import os


class Disk:
    def __init__(self, path):
        self.path = path
        self.fp = None
        self.total = 0
        self.open()

    def open(self):
        if not os.path.exists(self.path):
            raise FileNotFoundError(f"Image not found: {self.path}")
        self.fp = open(self.path, "rb")
        self.total = os.path.getsize(self.path)

    def read(self, offset, size=512):
        if offset < 0 or offset >= self.total:
            return b""
        self.fp.seek(offset)
        return self.fp.read(min(size, self.total - offset))

    def sector(self, lba, size=512):
        offset = lba * size
        return self.read(offset, size)

    def cluster(self, k, data_lba, spc=8, bps=512):
        if k < 2:
            return b""
        offset = (data_lba + (k - 2) * spc) * bps
        csize = spc * bps
        return self.read(offset, csize)

    def size(self):
        return self.total

    def close(self):
        if self.fp and not self.fp.closed:
            self.fp.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def execute(disk, info, args, chain=None):
    cluster = args.get("cluster")
    if cluster is None:
        return "Error: cluster parameter is required for disk_read."
    size = args.get("size")
    data_lba = info.get("data_lba", 0)
    spc = info.get("spc", 1)
    bps = info.get("bps", 512)
    raw = disk.cluster(cluster, data_lba, spc, bps)
    if not raw or not any(raw):
        return f"Cluster {cluster} is empty or unallocated."
    if size:
        raw = raw[:size]
    safe_chars = [chr(b) if (32 <= b <= 126 or b in (10, 9)) and b != 27 else "." for b in raw]
    head = "".join(safe_chars[:200])
    tail = "".join(safe_chars[-200:])
    seam_info = ""
    if chain:
        prev_c = chain[-1]
        prev_raw = disk.cluster(prev_c, data_lba, spc, bps)
        prev_tail = "".join(chr(b) if (32 <= b <= 126 or b in (10, 9)) and b != 27 else "." for b in prev_raw[-120:]).strip()
        c_head = "".join(chr(b) if (32 <= b <= 126 or b in (10, 9)) and b != 27 else "." for b in raw[:120]).strip()
        seam_info = f"\n[Preview]:\nTail of cluster {prev_c}: ...{prev_tail}\nHead of cluster {cluster}: {c_head}...\nCombined: ...{prev_tail} {c_head}..."
    return f"Cluster {cluster} content {len(raw)} bytes:\n[Head]:\n{head}\n[Tail]:\n{tail}{seam_info}"