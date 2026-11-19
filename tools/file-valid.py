import ast
import re
import json
import io
import struct
import zipfile
import zlib


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


def validate_rust(code_str):
    ok, err = check_brackets(code_str)
    if not ok:
        return False, err
    has_keywords = bool(re.search(r"\b(fn|let|mut|struct|enum|impl|pub|match|use|mod|trait|unsafe|where|type)\b", code_str))
    if not has_keywords:
        return False, "Missing Rust language keywords"
    return True, None


def validate_go(code_str):
    ok, err = check_brackets(code_str)
    if not ok:
        return False, err
    has_keywords = bool(re.search(r"\b(package|import|func|type|struct|interface|var|const|chan|defer|go|select|return)\b", code_str))
    if not has_keywords:
        return False, "Missing Go language keywords"
    return True, None


def validate_js(code_str):
    ok, err = check_brackets(code_str)
    if not ok:
        return False, err
    has_keywords = bool(re.search(r"\b(function|const|let|var|return|import|export|class|async|await|interface|type)\b", code_str))
    if not has_keywords:
        return False, "Missing JavaScript or TypeScript language keywords"
    return True, None


def validate_java(code_str):
    ok, err = check_brackets(code_str)
    if not ok:
        return False, err
    has_keywords = bool(re.search(r"\b(package|import|public|class|interface|private|protected|static|final|void|return|new)\b", code_str))
    if not has_keywords:
        return False, "Missing Java language keywords"
    return True, None


def validate_json(code_str):
    try:
        json.loads(code_str)
        return True, None
    except Exception as e:
        return False, f"JSON syntax error: {e}"


def validate_zip(content):
    raw = content if isinstance(content, (bytes, bytearray)) else content.encode("utf-8", errors="ignore")
    if len(raw) < 22 or not raw.startswith(b"PK\x03\x04"):
        return False, "Invalid ZIP header"
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            bad_file = zf.testzip()
            if bad_file is not None:
                return False, f"Corrupted file inside archive: {bad_file}"
            return True, None
    except Exception as e:
        return False, f"ZIP validation error: {e}"


def validate_ole(content):
    raw = content if isinstance(content, (bytes, bytearray)) else content.encode("utf-8", errors="ignore")
    if len(raw) < 512 or not raw.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"):
        return False, "Invalid OLE2 compound file header"
    sector_shift = struct.unpack_from("<H", raw, 0x1E)[0]
    if sector_shift not in (9, 12):
        return False, "Invalid OLE2 sector shift"
    return True, None


def validate_png(content):
    raw = content if isinstance(content, (bytes, bytearray)) else content.encode("utf-8", errors="ignore")
    if len(raw) < 16 or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return False, "Invalid PNG signature"
    if b"IEND" not in raw:
        return False, "Missing PNG IEND chunk"
    pos = 8
    idat_parts = []
    while pos + 8 <= len(raw):
        length, ctype = struct.unpack(">I4s", raw[pos:pos+8])
        pos += 8
        if pos + length + 4 > len(raw):
            return False, f"Truncated PNG chunk data for {ctype}"
        cdata = raw[pos:pos+length]
        pos += length
        crc = struct.unpack(">I", raw[pos:pos+4])[0]
        pos += 4
        calc_crc = zlib.crc32(ctype + cdata) & 0xFFFFFFFF
        if crc != calc_crc:
            return False, f"PNG CRC mismatch in {ctype.decode('ascii', errors='ignore')} chunk"
        if ctype == b"IDAT":
            idat_parts.append(cdata)
        elif ctype == b"IEND":
            break
    if idat_parts:
        try:
            zlib.decompress(b"".join(idat_parts))
        except Exception as e:
            return False, f"Corrupted PNG image stream: {e}"
    return True, None


def validate_jpg(content):
    raw = content if isinstance(content, (bytes, bytearray)) else content.encode("utf-8", errors="ignore")
    if len(raw) < 4 or not raw.startswith(b"\xFF\xD8\xFF"):
        return False, "Invalid JPEG SOI header"
    if b"\xFF\xD9" not in raw:
        return False, "Missing JPEG EOI marker"
    return True, None


def validate_pdf(content):
    raw = content if isinstance(content, (bytes, bytearray)) else content.encode("utf-8", errors="ignore")
    if len(raw) < 8 or not raw.startswith(b"%PDF-"):
        return False, "Invalid PDF header"
    if b"%%EOF" not in raw:
        return False, "Missing PDF EOF marker"
    return True, None


def validate(content, lang):
    raw = content if isinstance(content, (bytes, bytearray)) else str(content).encode("utf-8", errors="ignore")
    lang = lang.lower().lstrip(".")

    if lang in ("zip", "docx", "xlsx", "pptx"):
        return validate_zip(raw)
    elif lang in ("ole", "doc", "xls", "ppt"):
        if raw.startswith(b"PK\x03\x04"):
            return validate_zip(raw)
        return validate_ole(raw)
    elif lang == "png":
        return validate_png(raw)
    elif lang in ("jpg", "jpeg"):
        return validate_jpg(raw)
    elif lang == "pdf":
        return validate_pdf(raw)

    text = raw.decode("utf-8", errors="ignore")

    if lang == "py":
        return validate_python(text)
    elif lang in ("c", "cpp", "h"):
        return validate_c(text)
    elif lang == "cs":
        return validate_cs(text)
    elif lang in ("rs", "rust"):
        return validate_rust(text)
    elif lang in ("go", "golang"):
        return validate_go(text)
    elif lang in ("js", "jsx", "ts", "tsx"):
        return validate_js(text)
    elif lang == "java":
        return validate_java(text)
    elif lang == "json":
        return validate_json(text)

    # Default validation fallback for generic plain text files
    return True, None


def execute(disk, info, args, default_lang="c", target_size=None, needed=None):
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

    c_repr = f"[{chain[0]}..{chain[-1]}] {len(chain)} clusters" if len(chain) > 10 else str(chain)

    if needed and len(chain) == needed:
        ok, err = validate(payload, lang)
        if ok:
            return f"Chain {c_repr} is VALID for {lang}. Complete file 100%."
        return f"Chain {c_repr} is INVALID for {lang}. Error: {err}"

    code_langs = {"c", "cpp", "h", "cs", "rs", "rust", "go", "golang", "js", "jsx", "ts", "tsx", "java", "py", "json"}
    norm_lang = lang.lower().lstrip(".")
    if norm_lang in code_langs:
        ok, err = check_brackets(payload.decode("utf-8", errors="ignore"))
        if not ok and err and "Unmatched" in err:
            return f"Chain {c_repr} is INVALID for {lang}. Rogue closing bracket: {err}"

    return f"Chain {c_repr} is VALID for {lang}. Structural continuity verified."