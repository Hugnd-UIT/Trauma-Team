import os
import sys
import json
import importlib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

disk_read = importlib.import_module("tools.disk-read")
hex_dump = importlib.import_module("tools.hex-dump")
hex_search = importlib.import_module("tools.hex-search")
file_valid = importlib.import_module("tools.file-valid")
file_export = importlib.import_module("tools.file-export")
detect = importlib.import_module("src.detect")
build = importlib.import_module("src.build")
router = importlib.import_module("file-systems.router")

from agent.llm import LLM
from agent import state, context, prompt
from utils.logger import setup_logger

BANNER = """
╔══════════════════════════════════════════════════════════════════════════════════════╗
║   ▄         ██████         ▄   ████████╗██████╗  █████╗ ██╗   ██╗███╗   ███╗ █████╗  ║
║   ██▄▄      ██████       ▄██   ╚══██╔══╝██╔══██╗██╔══██╗██║   ██║████╗ ████║██╔══██╗ ║
║   █████▄    ██████    ▄█████      ██║   ██████╔╝███████║██║   ██║██╔████╔██║███████║ ║
║   ████████▄ ██████ ▄▄███████      ██║   ██╔══██╗██╔══██║██║   ██║██║╚██╔╝██║██╔══██║ ║
║    ▀▀█████████████████████▀       ██║   ██║  ██║██║  ██║╚██████╔╝██║ ╚═╝ ██║██║  ██║ ║
║       ▀████████████████▀          ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝ ║
║          ▀██████████▀▀                                                               ║
║          ▄██████████▄▄                 ████████╗███████╗ █████╗ ███╗   ███╗          ║
║       ▄████████████████▄               ╚══██╔══╝██╔════╝██╔══██╗████╗ ████║          ║
║    ▄▄█████████████████████▄               ██║   █████╗  ███████║██╔████╔██║          ║
║   ████████▀ ██████ ▀▀███████              ██║   ██╔══╝  ██╔══██║██║╚██╔╝██║          ║
║   █████▀    ██████    ▀█████              ██║   ███████╗██║  ██║██║ ╚═╝ ██║          ║
║   ██▀▀      ██████       ▀██              ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝          ║
║   ▀         ██████         ▀                                                         ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
"""


def extract_runs(disk, runs, sectors_per_cluster, bytes_per_sector):
    parts = []
    cluster_size = sectors_per_cluster * bytes_per_sector
    for run_length, lcn in runs:
        offset = lcn * cluster_size
        parts.append(disk.read(offset, run_length * cluster_size))
    return b"".join(parts)


def recover_fat_multi(disk, item, info, bot, log):
    cluster_size = info["csize"]
    sectors_per_cluster = info["spc"]
    bytes_per_sector = info["bps"]
    data_lba = info["data_lba"]
    size = item["size"]
    needed = (size + cluster_size - 1) // cluster_size
    start_cluster = item["cluster"]
    name = item["name"]
    lang = item.get("lang") or "code"

    first_cluster_data = disk.cluster(start_cluster, data_lba, sectors_per_cluster, bytes_per_sector)
    if not first_cluster_data or not any(first_cluster_data):
        log.info(f"Starting cluster {start_cluster} is zeroed out. Skipping.")
        return b"", []

    chain = [start_cluster]
    user_prompt = prompt.USER.format(
        name=name,
        lang=lang,
        size=size,
        needed=needed,
        chain=chain,
        progress=len(chain)
    )
    messages = context.build(user_prompt)

    step = 0
    max_steps = max(25, needed * 4)
    recent_actions = []

    while step < max_steps and len(chain) < needed:
        step += 1
        sys.stdout.flush()

        text_response, tokens_in, tokens_out = bot.call(messages)
        state.token(tokens_in, tokens_out)

        if not text_response or text_response.startswith("[!]"):
            log.info(f"Error: {text_response}")
            break

        thought = ""
        tool = ""
        args = {}

        if isinstance(text_response, str):
            clean_resp = text_response.strip()
            if clean_resp.startswith("```"):
                resp_lines = clean_resp.splitlines()
                if resp_lines and resp_lines[0].startswith("```"):
                    resp_lines = resp_lines[1:]
                if resp_lines and resp_lines[-1].startswith("```"):
                    resp_lines = resp_lines[:-1]
                clean_resp = "\n".join(resp_lines).strip()

            try:
                data = json.loads(clean_resp)
                if isinstance(data, dict):
                    thought = data.get("thought", "")
                    tool = data.get("tool", "")
                    args = data.get("args", {})
            except Exception:
                pass

            if not tool and "{" in clean_resp and "}" in clean_resp:
                try:
                    s_idx = clean_resp.find("{")
                    e_idx = clean_resp.rfind("}") + 1
                    data = json.loads(clean_resp[s_idx:e_idx])
                    if isinstance(data, dict):
                        thought = data.get("thought", "")
                        tool = data.get("tool", "")
                        args = data.get("args", {})
                except Exception:
                    pass

        if not tool:
            tool = "hex_search"
            args = {"cluster": chain[-1], "radius": 50}

        action_key = f"{tool}:{json.dumps(args, sort_keys=True)}"
        recent_actions.append(action_key)
        loop_alert = ""
        if len(recent_actions) >= 2 and recent_actions[-1] == recent_actions[-2]:
            loop_alert = f"\nNotice: Repeated action {tool} detected. Inspect candidate clusters directly with disk_read or file_valid."

        if thought:
            log.info(f"Thought: {thought}")
        log.info(f"Action: {tool}: {json.dumps(args)}")

        obs = ""
        if tool in ["hex_search", "search_hex", "search"]:
            obs = hex_search.execute(disk, info, args, chain=chain, lang=lang) + loop_alert
        elif tool in ["disk_read", "read_cluster", "read"]:
            obs = disk_read.execute(disk, info, args, chain=chain)
            c = args.get("cluster")
            if isinstance(c, int) and c not in chain:
                val_res = file_valid.execute(disk, info, {"chain": chain + [c], "lang": lang}, needed=needed)
                if " is VALID" in val_res and "INVALID" not in val_res:
                    obs += f"\nValidation check: cluster {c} connects cleanly with chain {chain}. To confirm, call file_valid with chain {chain + [c]}."
                else:
                    obs += f"\nValidation warning: cluster {c} failed syntax verification: {val_res}"
        elif tool in ["file_valid", "validate_file", "validate"]:
            tool_lang = args.get("lang") or lang
            obs = file_valid.execute(disk, info, args, default_lang=tool_lang, target_size=size, needed=needed)
            if " is VALID" in obs and "INVALID" not in obs:
                chain_arg = args.get("chain", [])
                if isinstance(chain_arg, list) and len(chain_arg) > len(chain):
                    if chain_arg[:len(chain)] == chain:
                        chain = list(chain_arg)
                        lang = tool_lang
                        log.info(f"Observation: Cluster confirmed, chain updated -> {chain}")
            else:
                log.info(f"Observation: Cluster rejected or invalid. Current chain remains: {chain}")
                obs += f"\nCandidate cluster rejected. Chain remains {chain}. Please inspect other clusters."
        
        elif tool in ["file_export", "export_file", "export", "save"]:
            chain_arg = args.get("chain", chain)
            export_lang = args.get("lang") or lang
            test_payload = b"".join(
                disk.cluster(cid, data_lba, sectors_per_cluster, bytes_per_sector)
                for cid in chain_arg
            )[:size]
            is_valid, err = file_valid.validate(test_payload, export_lang)
            if is_valid and len(chain_arg) == needed:
                chain = list(chain_arg)
                lang = export_lang
                log.info(f"Observation: Chain {chain} verified 100% for export.")
                return test_payload, chain
            else:
                obs = f"Validation failed for export: {err}. Chain {chain_arg} is invalid. Current chain remains {chain}. Continue searching."
                log.info(f"Observation: {obs}")
        else:
            obs = f"Unknown tool: {tool}. Available tools: hex_search, disk_read, file_valid, file_export."

        log.info(f"Observation: {obs}")

        next_user_prompt = prompt.USER.format(
            name=name,
            lang=lang,
            size=size,
            needed=needed,
            chain=chain,
            progress=len(chain)
        )
        combined_message = f"{next_user_prompt}\n\nObservation from {tool}:\n{obs}\n\nObserve the tool result and decide on the next action."

        messages.append({"role": "assistant", "content": text_response})
        messages.append({"role": "user", "content": combined_message})

        if len(chain) == needed:
            test_payload = b"".join(
                disk.cluster(cid, data_lba, sectors_per_cluster, bytes_per_sector)
                for cid in chain
            )[:size]
            is_valid, err = file_valid.validate(test_payload, lang)
            if is_valid:
                return test_payload, chain
            else:
                bad_cluster = chain.pop()
                log.info(f"Validation failed for complete chain with cluster {bad_cluster}: {err}. Rolling back to chain {chain}.")
                obs += f"\nValidation check failed for complete file: {err}. Cluster {bad_cluster} rolled back. Chain is now {chain}. Try another candidate."

    final_payload = b"".join(
        disk.cluster(cid, data_lba, sectors_per_cluster, bytes_per_sector)
        for cid in chain
    )[:size]
    is_valid, _ = file_valid.validate(final_payload, lang)
    if is_valid and len(chain) == needed:
        return final_payload, chain
    return b"", []


def load_env():
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as file_pointer:
            for line in file_pointer:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


def save_info_report(img_path, info, items, results):
    os.makedirs("outputs", exist_ok=True)
    report_path = os.path.join("outputs", "info.json")
    with open(report_path, "w", encoding="utf-8") as file_pointer:
        json.dump({
            "image": img_path,
            "fs": info,
            "total_items": len(items),
            "recovered_count": len(results),
            "recovered_files": results
        }, file_pointer, indent=2)


def run(img_path):
    try:
        sys.stdout.write("\033(B\033)B\017\033[0m")
        sys.stdout.flush()
    except Exception:
        pass
    load_env()
    log = setup_logger("outputs/recovery.log")
    for b_line in BANNER.strip().splitlines():
        log.info(b_line)

    with disk_read.Disk(img_path) as disk:
        info = detect.detect(disk)
        fs_type = info.get("fs", "UNKNOWN")
        log.info(f"Image: {img_path}")
        log.info(f"File system: {fs_type}")

        state.init(image=img_path, fs=fs_type)
        items = router.scan(disk, info)
        log.info(f"Directory: {len(items)}")

        non_sys = [item for item in items if not item["name"].startswith("$")]
        tree_lines = build.render(build.build_dict(non_sys))
        for t_line in tree_lines:
            log.info(t_line)

        deleted_files = [item for item in items if item.get("deleted") and not item.get("is_dir")]
        bot = LLM()
        results = []
        save_info_report(img_path, info, items, results)

        for item in deleted_files:
            name = item["name"]
            size = item.get("size", 0)
            lang = item.get("lang") or "txt"
            chain = []
            payload = b""

            log.info(f"=== Processing: {name} - {size} bytes - lang: {lang} ===")

            if item.get("carved") and item.get("payload") is not None:
                payload = item["payload"]
                chain = [item.get("cluster", 0)]
                log.info(f"Method: Binary raw carve - {lang}")

            elif item.get("resident") and item.get("resident_data") is not None:
                payload = item["resident_data"][:size]
                chain = ["Resident"]
                log.info("Method: NTFS single cluster")

            elif fs_type == "NTFS" and item.get("runs"):
                runs = item["runs"]
                payload = extract_runs(disk, runs, info["spc"], info["bps"])[:size]
                chain = [r[1] for r in runs]
                log.info("Method: NTFS multi clusters")

            elif fs_type.startswith("FAT") and size <= info["csize"]:
                single_cluster = item.get("cluster", 0)
                payload = disk.cluster(single_cluster, info["data_lba"], info["spc"], info["bps"])[:size]
                chain = [single_cluster]
                log.info("Method: FAT single cluster")

            elif fs_type.startswith("FAT") and size > info["csize"]:
                log.info("Method: FAT multi clusters")
                payload, chain = recover_fat_multi(disk, item, info, bot, log)
                if chain:
                    log.info(f"Final chain: {chain}")

            if not chain or not payload:
                log.info("[!] FAILED: Unrecoverable!")
                state.update(name, "failed", chain=[])
                save_info_report(img_path, info, items, results)
                continue

            valid, err = file_valid.validate(payload, lang)
            if not valid:
                log.info(f"[!] FAILED: AST verification failed: {err}")
                state.update(name, "failed", chain=chain)
                save_info_report(img_path, info, items, results)
                continue
            else:
                log.info(f"[+] Done. Verified: PASSED 100% - {lang} grammar valid")

            res = file_export.save(payload, name, size=size, chain=chain)
            state.update(name, "done", chain=chain)
            results.append(res)
            log.info(f"Saved -> {res['path']}")
            log.info(f"SHA-256: {res['sha256']}")
            save_info_report(img_path, info, items, results)

        save_info_report(img_path, info, items, results)
        log.info("=== MISSION COMPLETE ===")
        log.info(f"[+] Done. Files recovered: {len(results)} / {len(deleted_files)}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else r"G:\My Drive\NT212\assign\FAT.img"
    run(target)
