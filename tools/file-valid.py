import ast
import re


def check_brackets(text):
    stack = []
    pairs = {")": "(", "}": "{", "]": "["}
    in_string = False
    str_char = ""

    for i, ch in enumerate(text):
        if ch in ('"', "'") and (i == 0 or text[i - 1] != "\\"):
            if not in_string:
                in_string = True
                str_char = ch
            elif str_char == ch:
                in_string = False
            continue

        if in_string:
            continue

        if ch in pairs.values():
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack[-1] != pairs[ch]:
                return False, f"Unmatched '{ch}'"
            stack.pop()

    if stack:
        return False, f"Unclosed '{stack[-1]}'"
    return True, None


def validate_python(code_str):
    try:
        ast.parse(code_str)
        return True, None
    except SyntaxError as e:
        return False, f"SyntaxError: {e.msg} at line {e.lineno}"


def validate_c(code_str):
    ok, err = check_brackets(code_str)
    if not ok:
        return False, err
    has_keywords = bool(re.search(r"\b(int|void|char|return|if|for|while|include|struct|class)\b", code_str))
    if not has_keywords:
        return False, "Missing C/C++ language keywords"
    return True, None


def validate_cs(code_str):
    ok, err = check_brackets(code_str)
    if not ok:
        return False, err
    has_keywords = bool(re.search(r"\b(using|namespace|class|public|private|static|void|string|int)\b", code_str))
    if not has_keywords:
        return False, "Missing C# language keywords"
    return True, None


def validate(content, lang):
    text = content.decode("utf-8", errors="ignore") if isinstance(content, bytes) else str(content)
    lang = lang.lower().lstrip(".")

    if lang == "py":
        return validate_python(text)
    elif lang in ("c", "cpp", "h"):
        return validate_c(text)
    elif lang == "cs":
        return validate_cs(text)

    # Default validation fallback for generic plain text files
    return True, None


def execute(disk, info, args, default_lang="c", target_size=None, needed=None):
    chain = args.get("chain", [])
    if not chain:
        return "Error: chain parameter is empty."
    lang = args.get("lang") or default_lang
    data_lba = info.get("data_lba", 0)
    spc = info.get("spc", 1)
    bps = info.get("bps", 512)
    parts = []
    for c in chain:
        parts.append(disk.cluster(c, data_lba, spc, bps))
    payload = b"".join(parts)
    if target_size:
        payload = payload[:target_size]

    if needed and len(chain) == needed:
        ok, err = validate(payload, lang)
        if ok:
            return f"Chain {chain} is VALID for {lang}. Complete file 100%."
        return f"Chain {chain} is INVALID for {lang}. Error: {err}"

    ok, err = check_brackets(payload.decode("utf-8", errors="ignore"))
    if not ok and err and "Unmatched" in err:
        return f"Chain {chain} is INVALID for {lang}. Rogue closing bracket: {err}"

    return f"Chain {chain} is VALID for {lang}. Structural continuity verified."