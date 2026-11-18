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


def find_candidates(disk, current_cluster, data_lba, sectors_per_cluster, bytes_per_sector, radius=50, limit=4, exclude=None):
    # Scan surrounding clusters using Shannon entropy and printable ASCII screening
    cluster_size = sectors_per_cluster * bytes_per_sector
    total_clusters = (disk.size() - data_lba * bytes_per_sector) // cluster_size + 2
    candidates = []
    seen = set(exclude or [])
    seen.add(current_cluster)

    # Prioritize forward allocation proximity where subsequent fragments reside
    check_order = [cluster_id for cluster_id in range(current_cluster + 1, min(total_clusters, current_cluster + radius + 1))]
    check_order += [cluster_id for cluster_id in range(current_cluster - 1, max(1, current_cluster - radius - 1), -1)]

    for cluster_id in check_order:
        if cluster_id in seen:
            continue
        raw_cluster_bytes = disk.cluster(cluster_id, data_lba, sectors_per_cluster, bytes_per_sector)
        if not raw_cluster_bytes or raw_cluster_bytes[:4] == b"\x00\x00\x00\x00":
            continue

        stripped_cluster_bytes = raw_cluster_bytes.rstrip(b"\x00")
        if not stripped_cluster_bytes:
            continue

        sample = stripped_cluster_bytes[:64]
        ascii_chars = sum(1 for byte_val in sample if 32 <= byte_val <= 126 or byte_val in [10, 13, 9])
        if ascii_chars / len(sample) < 0.70:
            continue

        cluster_entropy = entropy(stripped_cluster_bytes)
        if 2.5 <= cluster_entropy <= 7.0:
            preview_text = "".join(chr(b) if 32 <= b <= 126 else " " for b in stripped_cluster_bytes[:80]).strip()
            candidates.append({"cluster": cluster_id, "entropy": round(cluster_entropy, 2), "preview": preview_text})
            if len(candidates) >= limit:
                break

    return candidates


def search(disk, data_lba, sectors_per_cluster, bytes_per_sector, cluster=None, radius=50, limit=5, pattern=None, exclude=None):
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
        return find_candidates(disk, cluster, data_lba, sectors_per_cluster, bytes_per_sector, radius=radius, limit=limit, exclude=exclude)
    return results


def execute(disk, info, args, chain=None):
    cluster = args.get("cluster")
    if cluster is None and chain:
        cluster = chain[-1]
    if cluster is None:
        cluster = 2
    radius = args.get("radius", 50)
    limit = args.get("limit", 8)
    pattern = args.get("pattern")
    cands = search(
        disk,
        info["data_lba"],
        info["spc"],
        info["bps"],
        cluster=cluster,
        radius=radius,
        limit=limit,
        pattern=pattern,
        exclude=chain
    )
    if not cands:
        return f"No candidate clusters found within radius {radius} around cluster {cluster}."
    lines = []
    if chain:
        prev_c = chain[-1]
        prev_raw = disk.cluster(prev_c, info["data_lba"], info["spc"], info["bps"])
        prev_tail = prev_raw[-120:].decode("utf-8", errors="replace").strip()
        lines.append(f"Current chain tail from cluster {prev_c}:\n...{prev_tail}\n")
    lines.append(f"Found {len(cands)} candidate cluster entries:")
    for c in cands:
        lines.append(f"- Cluster {c['cluster']}: entropy={c.get('entropy', 0.0)} preview='{c.get('preview', '')}'")
    return "\n".join(lines)
