import json
import importlib

file_valid = importlib.import_module("tools.file-valid")


def format_hex(raw_bytes, max_bytes=512):
    lines = []
    shown = raw_bytes[:max_bytes]

    for off in range(0, len(shown), 16):
        chunk = shown[off:off + 16]
        hex_str = " ".join(f"{b:02x}" for b in chunk)
        ascii_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"{off:04x}: {hex_str:<48}  |{ascii_str}|")

    return "\n".join(lines)


def execute(disk, info, args, target_size=None, fallback_chain=None, lang="code"):
    chain = file_valid.parse_chain(args, fallback_chain=fallback_chain)
    if not chain:
        return "Error: chain is empty. Provide cluster chain of the file to read."

    mode = args.get("mode", "tail").lower()

    try:
        count = int(args.get("count", args.get("clusters", 1)))
    except Exception:
        count = 1

    count = max(1, min(count, len(chain)))

    if mode == "head":
        selected_clusters = chain[:count]

    elif mode == "range":
        start_c = args.get("start_cluster", args.get("from_cluster", chain[0]))
        end_c = args.get("end_cluster", args.get("to_cluster", chain[-1]))

        try:
            start_c = int(start_c)
            end_c = int(end_c)
        except Exception:
            start_c = chain[0]
            end_c = chain[-1]

        if start_c in chain and end_c in chain:
            s_idx = chain.index(start_c)
            e_idx = chain.index(end_c)

            if s_idx <= e_idx:
                selected_clusters = chain[s_idx:e_idx + 1]
            else:
                selected_clusters = chain[e_idx:s_idx + 1]

        else:
            selected_clusters = [c for c in chain if min(start_c, end_c) <= c <= max(start_c, end_c)]
            if not selected_clusters:
                selected_clusters = chain[-count:]

    else:
        selected_clusters = chain[-count:]

    data_lba = info.get("data_lba", 0)
    spc = info.get("spc", 1)
    bps = info.get("bps", 512)

    parts = []
    for c in selected_clusters:
        parts.append(disk.cluster(c, data_lba, spc, bps))

    payload = b"".join(parts)

    clean_lang = (args.get("lang") or lang or "code").lower().lstrip(".")
    is_binary = clean_lang in [
        "png", "jpg", "jpeg", "zip", "docx", "xlsx", "pptx",
        "pdf", "ole", "doc", "xls", "ppt", "bin"
    ]

    if len(selected_clusters) <= 10:
        c_repr = str(selected_clusters)
    else:
        c_repr = f"[{selected_clusters[0]}..{selected_clusters[-1]}] ({len(selected_clusters)} clusters)"

    header = f"=== File content of clusters {c_repr} ==="

    if is_binary:
        preview = format_hex(payload)
        return f"{header}\n{preview}"

    text = payload.decode("utf-8", errors="ignore").rstrip("\x00")
    lines = text.splitlines()

    out_lines = [header]
    for i, line in enumerate(lines, 1):
        out_lines.append(f"{i:4d} | {line}")

    return "\n".join(out_lines)
