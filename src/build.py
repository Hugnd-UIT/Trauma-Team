def format_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def build_dict(items):
    tree = {"name": "/", "is_dir": True, "children": {}, "item": None}

    for item in items:
        path = item.get("path", "").strip("/")
        if not path:
            continue
        parts = path.split("/")
        curr = tree

        for i, p in enumerate(parts):
            is_last = i == len(parts) - 1
            if is_last:
                curr["children"][p] = {
                    "name": p,
                    "is_dir": item.get("is_dir", False),
                    "children": {},
                    "item": item
                }
            else:
                if p not in curr["children"]:
                    curr["children"][p] = {
                        "name": p,
                        "is_dir": True,
                        "children": {},
                        "item": None
                    }
                curr = curr["children"][p]

    return tree


def render(node, prefix="", is_last=True):
    lines = []
    connector = "└── " if is_last else "├── "
    name = node["name"]
    item = node.get("item")

    if name != "/":
        if item:
            status = "[DELETED]" if item.get("deleted") else "[ACTIVE]"
            size_str = format_size(item.get("size", 0))
            is_d = item.get("is_dir", False)
            if is_d:
                line = f"{prefix}{connector}📁 {name}/"
            else:
                line = f"{prefix}{connector}{name} {status} {size_str}"
        else:
            line = f"{prefix}{connector}📁 {name}/"
        lines.append(line)
        child_prefix = prefix + ("    " if is_last else "│   ")
    else:
        lines.append("📁 /")
        child_prefix = ""

    children = list(node["children"].values())
    for i, child in enumerate(children):
        last_child = i == len(children) - 1
        if name != "/":
            if i == 0:
                lines.append(f"{child_prefix}│")
        lines.extend(render(child, child_prefix, last_child))
        if name == "/" and not last_child:
            lines.append("│")

    return lines


def print_tree(items):
    tree = build_dict(items)
    lines = render(tree)
    output = "\n".join(lines)
    print(output)
    return output
