import json

tree = {}
done = []
failed = []
history = []
facts = {}
tin = 0
tout = 0


def init(image="", fs=""):
    global tree, done, failed, history, facts, tin, tout
    tree = {
        "image": image,
        "fs": fs,
        "files": [],
        "done": [],
        "failed": []
    }
    done = []
    failed = []
    history = []
    facts = {}
    tin = 0
    tout = 0


def record(step, action, detail, result):
    global history
    entry = {
        "step": step,
        "action": action,
        "detail": detail,
        "result": result
    }
    history.append(entry)


def update(file_name, status, chain=None):
    global tree, done, failed
    if status == "done":
        if file_name not in done:
            done.append(file_name)
        if file_name in failed:
            failed.remove(file_name)
    elif status == "fail":
        if file_name not in failed:
            failed.append(file_name)

    tree["done"] = done
    tree["failed"] = failed
    if chain:
        facts[file_name] = chain


def token(in_count, out_count):
    global tin, tout
    tin += in_count
    tout += out_count


def view():
    lines = [
        f"FS: {tree.get('fs', 'Unknown')} | Target: {tree.get('image', 'None')}",
        f"Done: {', '.join(done) or 'None'}",
        f"Failed: {', '.join(failed) or 'None'}",
        f"Tokens: {tin} in / {tout} out"
    ]
    return "\n".join(lines)


def dump():
    return json.dumps({
        "tree": tree,
        "facts": facts,
        "done": done,
        "failed": failed,
        "tin": tin,
        "tout": tout
    }, indent=2)
