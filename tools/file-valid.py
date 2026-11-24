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


def validate_c(code_str, strict_c=False):
    ok, err = check_brackets(code_str)
    if not ok:
        return False, err
    has_keywords = bool(re.search(r"\b(int|void|char|return|if|for|while|include|struct|class)\b", code_str))
    if not has_keywords:
        return False, "Missing C/C++ language keywords"
    if strict_c and re.search(r"\b(class\s+\w+|namespace\s+\w+|<iostream>|<vector>|std::)\b", code_str):
        return False, "C++ syntax detected in C source"
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


def validate_zip_stream(raw):
    if len(raw) < 4:
        return True, None
    if not raw.startswith(b"PK\x03\x04"):
        return False, "Invalid ZIP header: missing PK header"
    idx = 0
    while idx + 30 <= len(raw):
        sig = raw[idx:idx+4]
        if sig in (b"PK\x01\x02", b"PK\x05\x06"):
            break
        if sig != b"PK\x03\x04":
            return False, f"Corrupted ZIP stream at offset {idx}"
        flags, method = struct.unpack_from("<HH", raw, idx + 6)
        hdr_crc, hdr_csize, hdr_usize = struct.unpack_from("<III", raw, idx + 14)
        nlen, elen = struct.unpack_from("<HH", raw, idx + 26)
        fname = raw[idx+30:idx+30+nlen].decode("utf-8", errors="ignore")
        data_start = idx + 30 + nlen + elen
        if data_start > len(raw):
            break
        has_data_desc = (flags & 0x08) != 0
        if method == 0:
            csize = hdr_csize
            if data_start + csize <= len(raw):
                calc_crc = zlib.crc32(raw[data_start:data_start+csize]) & 0xFFFFFFFF
                if hdr_crc != 0 and calc_crc != hdr_crc:
                    return False, f"Corrupted file inside archive: {fname} CRC mismatch"
                idx = data_start + csize
            else:
                break
        elif method == 8:
            d = zlib.decompressobj(-15)
            chunk = raw[data_start:]
            try:
                decomp = d.decompress(chunk)
            except Exception as e:
                return False, f"Corrupted deflate stream inside archive: {fname}: {e}"
            if d.eof:
                consumed = len(chunk) - len(d.unused_data)
                curr_idx = data_start + consumed
                calc_crc = zlib.crc32(decomp) & 0xFFFFFFFF
                expected_crc = hdr_crc
                if has_data_desc and curr_idx + 4 <= len(raw) and raw[curr_idx:curr_idx+4] == b"PK\x07\x08":
                    if curr_idx + 16 <= len(raw):
                        expected_crc = struct.unpack_from("<I", raw, curr_idx + 4)[0]
                        curr_idx += 16
                elif has_data_desc and curr_idx + 12 <= len(raw) and raw[curr_idx:curr_idx+4] not in (b"PK\x03\x04", b"PK\x01\x02", b"PK\x05\x06"):
                    expected_crc = struct.unpack_from("<I", raw, curr_idx)[0]
                    curr_idx += 12
                if expected_crc != 0 and calc_crc != expected_crc:
                    return False, f"Corrupted file inside archive: {fname} CRC mismatch"
                idx = curr_idx
            else:
                break
        else:
            break
    if b"PK\x05\x06" in raw:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                bad = zf.testzip()
                if bad is not None:
                    return False, f"Corrupted file inside archive: {bad}"
        except Exception as e:
            return False, f"ZIP archive error: {e}"
    return True, None


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
    if len(raw) > 512:
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(raw))
            img.verify()
        except Exception as e:
            return False, f"Corrupted JPEG image: {e}"
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

    text = raw.decode("utf-8", errors="ignore").rstrip("\x00")

    if lang == "py":
        return validate_python(text)
    elif lang == "c":
        return validate_c(text, strict_c=True)
    elif lang in ("cpp", "h"):
        return validate_c(text, strict_c=False)
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


def parse_chain(args, fallback_chain=None):
    raw = args.get("chain")
    if not raw and "ranges" in args:
        raw = args.get("ranges")
    elif not raw and "range" in args:
        raw = args.get("range")

    if raw is None:
        return []

    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, (list, int)):
                raw = parsed
        except Exception:
            pass

    if isinstance(raw, str):
        cleaned = raw.strip("[]() ")
        if ".." in cleaned:
            parts = [p.strip() for p in cleaned.split("..", 1)]
            try:
                s, e = int(parts[0]), int(parts[1])
                return list(range(s, e + 1)) if s <= e else list(range(s, e - 1, -1))
            except Exception:
                pass
        try:
            val = int(cleaned)
            if fallback_chain and val not in fallback_chain:
                return list(fallback_chain) + [val]
            return [val]
        except Exception:
            return []

    if isinstance(raw, int):
        if fallback_chain and raw not in fallback_chain:
            return list(fallback_chain) + [raw]
        return [raw]

    flat = []
    if isinstance(raw, list):
        if len(raw) == 2 and all(isinstance(x, (int, str)) for x in raw):
            try:
                s, e = int(raw[0]), int(raw[1])
                if "range" in args and not any(k in args for k in ("chain", "clusters")):
                    return list(range(s, e + 1)) if s <= e else list(range(s, e - 1, -1))
                if fallback_chain and s == fallback_chain[0] and e >= fallback_chain[-1]:
                    return list(range(s, e + 1)) if s <= e else list(range(s, e - 1, -1))
            except Exception:
                pass

        for item in raw:
            if isinstance(item, int):
                flat.append(item)
            elif isinstance(item, str):
                try:
                    flat.append(int(item))
                except Exception:
                    pass
            elif isinstance(item, (list, tuple)):
                if len(item) == 2 and all(isinstance(x, (int, str)) for x in item):
                    try:
                        s, e = int(item[0]), int(item[1])
                        if s <= e:
                            flat.extend(range(s, e + 1))
                        else:
                            flat.extend(range(s, e - 1, -1))
                    except Exception:
                        pass
                else:
                    for sub in item:
                        try:
                            flat.append(int(sub))
                        except Exception:
                            pass

        if fallback_chain and flat:
            if fallback_chain[0] not in flat:
                return list(fallback_chain) + [c for c in flat if c not in fallback_chain]

    return flat


def execute(disk, info, args, default_lang="c", target_size=None, needed=None, fallback_chain=None):
    if "chain" not in args and "ranges" not in args and "range" not in args:
        invalid_keys = [k for k in args if k not in ("lang",)]
        key_str = f" Found unknown keys: {invalid_keys}." if invalid_keys else ""
        return f"Error: file_valid requires 'chain' parameter with cluster list or ranges.{key_str} Example: file_valid: {{\"chain\": [[105, 201], [203, 204]]}}"

    chain = parse_chain(args, fallback_chain=fallback_chain)
    if not chain:
        return "Error: chain parameter is empty."
    lang = args.get("lang") or default_lang
    norm_lang = lang.lower().lstrip(".")
    data_lba = info.get("data_lba", 0)
    spc = info.get("spc", 1)
    bps = info.get("bps", 512)
    c_repr = f"[{chain[0]}..{chain[-1]}] {len(chain)} clusters" if len(chain) > 40 else str(chain)
    is_binary_format = norm_lang in ("zip", "docx", "xlsx", "pptx", "png", "jpg", "jpeg", "pdf", "ole")
    parts = []
    for i, c in enumerate(chain):
        c_bytes = disk.cluster(c, data_lba, spc, bps)
        is_last = (needed is not None and len(chain) == needed and i == len(chain) - 1)
        if not is_last and len(c_bytes.rstrip(b"\x00")) < 64:
            return f"Chain {c_repr} is INVALID for {lang}. Cluster {c} is truncated or zeroed out."
        if is_binary_format:
            stripped = c_bytes.rstrip(b"\x00")
            if not is_last and (needed is None or len(chain) < needed or i < len(chain) - 1):
                if len(stripped) < len(c_bytes) - 512:
                    return f"Chain {c_repr} is INVALID for {lang}. Cluster {c} has trailing null padding and is not a full cluster."
            if len(stripped) >= 64:
                non_ascii = sum(1 for b in stripped if b > 126 or (b < 32 and b not in (9, 10, 13)))
                if non_ascii == 0 and not any(sig in c_bytes for sig in (b"PK\x03\x04", b"PK\x01\x02", b"PK\x05\x06", b"\x89PNG", b"\xFF\xD8", b"%PDF")):
                    return f"Chain {c_repr} is INVALID for {lang}. Cluster {c} is plain ASCII text, not binary."
        parts.append(c_bytes)
    payload = b"".join(parts)
    if target_size:
        payload = payload[:target_size]

    if needed and len(chain) == needed:
        ok, err = validate(payload, lang)
        if ok:
            return f"Chain {c_repr} is VALID for {lang}. Complete file 100%."
        return f"Chain {c_repr} is INVALID for {lang}. Error: {err}"

    if norm_lang in ("zip", "docx", "xlsx", "pptx"):
        ok, err = validate_zip_stream(payload)
        if not ok:
            return f"Chain {c_repr} is INVALID for {lang}. {err}"

    code_langs = {"c", "cpp", "h", "cs", "rs", "rust", "go", "golang", "js", "jsx", "ts", "tsx", "java", "py", "json"}
    if norm_lang in code_langs:
        text_stream = payload.decode("utf-8", errors="ignore")
        if norm_lang == "c" and re.search(r"\b(class\s+\w+|namespace\s+\w+|<iostream>|<vector>|std::)\b", text_stream):
            return f"Chain {c_repr} is INVALID for {lang}. C++ syntax detected in C source."

        # Verify syntactic continuity across statements
        clean_code = re.sub(r"//.*|/\*.*?\*/", " ", text_stream, flags=re.DOTALL)
        clean_code = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', " ", clean_code)
        tokens = re.findall(r"[a-zA-Z_]\w*|[^\s\w]", clean_code)
        qualifiers = {
            "const", "static", "unsigned", "signed", "long", "short",
            "inline", "virtual", "friend", "extern", "register",
            "volatile", "mutable", "constexpr", "template", "typename",
            "case", "goto", "sizeof"
        }
        starters = {
            "int", "void", "char", "float", "double", "bool",
            "class", "struct", "namespace", "return", "if", "for", "while", "switch"
        }
        for idx in range(len(tokens) - 1):
            t1, t2 = tokens[idx], tokens[idx + 1]
            if re.match(r"^[a-zA-Z_]\w*$", t1) and re.match(r"^[a-zA-Z_]\w*$", t2):
                if t2 in starters and t1 not in qualifiers:
                    return f"Chain {c_repr} is INVALID for {lang}. Syntax error at statement boundary: '{t1} {t2}' missing delimiter."
        ok, err = check_brackets(text_stream)
        if not ok and err and "Unmatched" in err:
            return f"Chain {c_repr} is INVALID for {lang}. Rogue closing bracket: {err}"

    return f"Chain {c_repr} is VALID for {lang}. Structural continuity verified."