import os
import sys
import logging
from pathlib import Path
import re

if os.name == "nt":
    os.system("")

RESET = "\033[0m"
GREY = "\033[90m"
BOLD_WHITE = "\033[1;37m"
YELLOW = "\033[1;33m"
GREEN = "\033[1;32m"
RED = "\033[1;31m"
BLUE = "\033[1;34m"
BOLD_CYAN = "\033[1;36m"


def format_record(record):
    raw = record.getMessage()

    if raw.startswith("╔") or raw.startswith("║") or raw.startswith("╚"):
        return f"{BLUE}{raw}{RESET}"

    stripped = raw.strip()
    if stripped.startswith("📁") or stripped.startswith("├──") or stripped.startswith("│") or stripped.startswith("└──"):
        return raw

    if raw.startswith("===") and raw.endswith("==="):
        msg = f"{BOLD_CYAN}{raw}{RESET}"
    elif raw.startswith("[!] FAILED:") or raw.startswith("Error:"):
        msg = f"{RED}{raw}{RESET}"
    elif raw.startswith("[+] Done."):
        msg = f"{GREEN}{raw}{RESET}"
    else:
        msg = raw

    if "Thought:" in msg:
        msg = msg.replace("Thought:", f"{GREEN}Thought:{RESET}")
    if "Action:" in msg:
        msg = msg.replace("Action:", f"{RED}Action:{RESET}")
    if "Observation:" in msg:
        msg = msg.replace("Observation:", f"{YELLOW}Observation:{RESET}")

    time_str = logging.Formatter().formatTime(record, "%H:%M:%S")
    return f"\n{GREY}[{time_str}]{RESET} {msg}"


def http_filter(record):
    return "HTTP Request:" not in record.getMessage()


def setup_logger(log_file=None):
    for lib in ["httpx", "httpx2", "httpcore", "httpcore2", "openai", "urllib3"]:
        logging.getLogger(lib).setLevel(logging.WARNING)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    formatter = logging.Formatter()
    formatter.format = format_record

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(http_filter)
    root.addHandler(handler)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ansi_re = re.compile(r"\x1b\[[0-9;]*m")

        class FlushingFileHandler(logging.FileHandler):
            def emit(self, record):
                super().emit(record)
                self.flush()

        file_handler = FlushingFileHandler(log_path, encoding="utf-8")
        file_handler.addFilter(http_filter)

        def format_file_record(rec):
            raw = rec.getMessage()
            if raw.startswith("╔") or raw.startswith("║") or raw.startswith("╚"):
                return raw
            stripped = raw.strip()
            if stripped.startswith("📁") or stripped.startswith("├──") or stripped.startswith("│") or stripped.startswith("└──"):
                return raw
            time_str = logging.Formatter().formatTime(rec, "%H:%M:%S")
            clean_msg = ansi_re.sub("", raw).lstrip("\r\n")
            return f"\n[{time_str}] {clean_msg}"

        file_formatter = logging.Formatter()
        file_formatter.format = format_file_record
        file_handler.setFormatter(file_formatter)
        root.addHandler(file_handler)

    logger = logging.getLogger("trauma-team")
    logger.setLevel(logging.INFO)
    return logger


__all__ = ["setup_logger", "format_record", "http_filter"]
