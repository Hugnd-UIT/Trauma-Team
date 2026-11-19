import math


def entropy(raw):
    # Calculate Shannon information entropy across raw byte distribution
    if not raw:
        return 0.0
    counts = [0] * 256
    for byte_value in raw:
        counts[byte_value] += 1
    total_bytes = len(raw)
    entropy_value = 0.0
    for frequency in counts:
        if frequency > 0:
            probability = frequency / total_bytes
            entropy_value -= probability * math.log2(probability)
    return entropy_value


def search_pattern(disk, pattern, max_results=5, chunk_size=1048576):
    # Search for specific byte sequence across physical disk image
    pattern_bytes = pattern.encode("utf-8") if isinstance(pattern, str) else pattern
    hits = []
    total_size = disk.size()
    position = 0

    while position < total_size and len(hits) < max_results:
        chunk = disk.read(position, chunk_size + len(pattern_bytes))
        if not chunk:
            break
        index = 0
        while True:
            index = chunk.find(pattern_bytes, index)
            if index == -1:
                break
            hit_offset = position + index
            hits.append(hit_offset)
            if len(hits) >= max_results:
                break
            index += len(pattern_bytes)
        position += chunk_size

    return hits


def find_candidates(disk, current_cluster, data_lba, sectors_per_cluster, bytes_per_sector, radius=50, limit=8, exclude=None, lang="code"):
    cluster_size = sectors_per_cluster * bytes_per_sector
    total_clusters = (disk.size() - data_lba * bytes_per_sector) // cluster_size + 2
    candidates = []
    seen = set(exclude or [])
    seen.add(current_cluster)

    check_order = [cluster_id for cluster_id in range(current_cluster + 1, min(total_clusters, current_cluster + radius + 1))]
    check_order += [cluster_id for cluster_id in range(current_cluster - 1, max(1, current_cluster - radius - 1), -1)]

    clean_lang = lang.lower().lstrip(".") if lang else "code"
    is_binary = clean_lang in ["png", "jpg", "jpeg", "zip", "docx", "xlsx", "pptx", "pdf", "ole", "doc", "xls", "ppt", "bin"]

    for cluster_id in check_order:
        if cluster_id in seen:
            continue
        raw_cluster_bytes = disk.cluster(cluster_id, data_lba, sectors_per_cluster, bytes_per_sector)
        if not raw_cluster_bytes or raw_cluster_bytes[:4] == b"\x00\x00\x00\x00":
            continue

        stripped_cluster_bytes = raw_cluster_bytes.rstrip(b"\x00")
        if not stripped_cluster_bytes:
            continue

        cluster_entropy = entropy(stripped_cluster_bytes)

        if is_binary:
            if cluster_entropy >= 2.0:
                preview_parts = []
                for b in stripped_cluster_bytes[:60]:
                    if 32 <= b <= 126:
                        preview_parts.append(chr(b))
                    else:
                        preview_parts.append(".")
                preview_text = "".join(preview_parts).strip()
                tag = ""
                if b"IEND" in stripped_cluster_bytes:
                    tag = " [PNG IEND marker found]"
                elif b"\xFF\xD9" in stripped_cluster_bytes:
                    tag = " [JPEG EOI marker found]"
                elif b"PK\x05\x06" in stripped_cluster_bytes:
                    tag = " [ZIP EOCD marker found]"
                elif b"PK\x01\x02" in stripped_cluster_bytes:
                    tag = " [ZIP Central Directory found]"
                elif b"PK\x03\x04" in stripped_cluster_bytes or b"PK" in stripped_cluster_bytes:
                    tag = " [ZIP/DOCX marker found]"
                elif b"%%EOF" in stripped_cluster_bytes:
                    tag = " [PDF EOF marker found]"
                elif b"\xD0\xCF\x11\xE0" in stripped_cluster_bytes or b"WordDocument" in stripped_cluster_bytes or b"Workbook" in stripped_cluster_bytes:
                    tag = " [OLE2 Compound Doc marker found]"
                candidates.append({"cluster": cluster_id, "entropy": round(cluster_entropy, 2), "preview": preview_text + tag})
                if len(candidates) >= limit:
                    break
        else:
            sample = stripped_cluster_bytes[:64]
            ascii_chars = sum(1 for byte_val in sample if 32 <= byte_val <= 126 or byte_val in [10, 13, 9])
            if ascii_chars / len(sample) < 0.65:
                continue

            if 2.5 <= cluster_entropy <= 7.0:
                preview_text = "".join(chr(b) if 32 <= b <= 126 else " " for b in stripped_cluster_bytes[:80]).strip()
                candidates.append({"cluster": cluster_id, "entropy": round(cluster_entropy, 2), "preview": preview_text})
                if len(candidates) >= limit:
                    break

    return candidates


def search(disk, data_lba, sectors_per_cluster, bytes_per_sector, cluster=None, radius=50, limit=8, pattern=None, exclude=None, lang="code"):
    results = []
    if pattern:
        hits = search_pattern(disk, pattern, max_results=limit * 2)
        for offset in hits:
            sector_number = offset // bytes_per_sector
            if sector_number >= data_lba:
                cluster_id = 2 + (sector_number - data_lba) // sectors_per_cluster
                if exclude and cluster_id in exclude:
                    continue
                results.append({"cluster": cluster_id, "offset": offset, "preview": str(pattern)})
                if len(results) >= limit:
                    break
    if not results and cluster is not None:
        return find_candidates(disk, cluster, data_lba, sectors_per_cluster, bytes_per_sector, radius=radius, limit=limit, exclude=exclude, lang=lang)
    return results


def execute(disk, info, args, chain=None, lang="code"):
    cluster = args.get("cluster")
    if cluster is None and chain:
        cluster = chain[-1]
    if cluster is None:
        cluster = 2
    radius = args.get("radius", 50)
    limit = args.get("limit", 8)
    pattern = args.get("pattern")
    search_lang = args.get("lang") or lang
    cands = search(
        disk,
        info["data_lba"],
        info["spc"],
        info["bps"],
        cluster=cluster,
        radius=radius,
        limit=limit,
        pattern=pattern,
        exclude=chain,
        lang=search_lang
    )
    if not cands:
        return f"No candidate clusters found within radius {radius} around cluster {cluster}."
    lines = []
    if chain:
        prev_c = chain[-1]
        prev_raw = disk.cluster(prev_c, info["data_lba"], info["spc"], info["bps"])
        prev_tail = "".join(chr(b) if (32 <= b <= 126 or b in (10, 9)) and b != 27 else "." for b in prev_raw[-120:]).strip()
        lines.append(f"Current chain tail from cluster {prev_c}:\n...{prev_tail}\n")
    lines.append(f"Found {len(cands)} candidate cluster entries:")
    for c in cands:
        lines.append(f"- Cluster {c['cluster']}: entropy={c.get('entropy', 0.0)} preview='{c.get('preview', '')}'")
    return "\n".join(lines)
