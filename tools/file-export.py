import os
import json
import hashlib


def save(data, filename, size=None, out_dir="outputs/recovered", chain=None):
    os.makedirs(out_dir, exist_ok=True)
    payload = data[:size] if size is not None else data

    # Sanitize filename
    safe_name = os.path.basename(filename).lstrip("_")
    out_path = os.path.join(out_dir, safe_name)

    with open(out_path, "wb") as f:
        f.write(payload)

    sha = hashlib.sha256(payload).hexdigest()

    # Update outputs/chain.json
    chain_path = os.path.join("outputs", "chain.json")
    os.makedirs(os.path.dirname(chain_path), exist_ok=True)
    chains = {}
    if os.path.exists(chain_path) and os.path.getsize(chain_path) > 0:
        try:
            with open(chain_path, "r", encoding="utf-8") as f:
                chains = json.load(f)
        except Exception:
            chains = {}

    chains[safe_name] = {
        "chain": chain or [],
        "size": len(payload),
        "sha256": sha
    }

    with open(chain_path, "w", encoding="utf-8") as f:
        json.dump(chains, f, indent=2)

    return {
        "status": "ok",
        "path": out_path,
        "size": len(payload),
        "sha256": sha
    }


def execute(disk, info, args, fallback_name=None, fallback_size=None):
    chain = args.get("chain", [])
    if not chain and "ranges" in args:
        chain = []
        for rng in args.get("ranges", []):
            if len(rng) == 2 and isinstance(rng[0], int) and isinstance(rng[1], int):
                chain.extend(range(rng[0], rng[1] + 1))
    elif not chain and "range" in args:
        rng = args.get("range", [])
        if len(rng) == 2 and isinstance(rng[0], int) and isinstance(rng[1], int):
            chain = list(range(rng[0], rng[1] + 1))
    if not chain:
        return "Error: chain parameter is empty for file_export."
    name = args.get("name") or fallback_name or "recovered.bin"
    size = args.get("size") or fallback_size
    data_lba = info.get("data_lba", 0)
    spc = info.get("spc", 1)
    bps = info.get("bps", 512)
    parts = []
    for c in chain:
        parts.append(disk.cluster(c, data_lba, spc, bps))
    payload = b"".join(parts)
    res = save(payload, name, size=size, chain=chain)
    return f"File exported successfully: path={res['path']} size={res['size']} sha256={res['sha256']}"

