"""Coverage projection of actual immutable Git outputs."""

import re

def coverage(comparison: str, include_paths: list[str], exclude_paths: list[str], diff: str, name_status: str | bytes, numstat: str | bytes) -> dict:
    """Make non-text or intentionally skipped Git inputs explicit to the workflow."""
    notices: list[dict] = []
    skipped: list[dict] = []
    name_records: list[tuple[str, list[str]]] = []
    if isinstance(name_status, bytes):
        tokens = [item.decode("utf-8", errors="replace") for item in name_status.split(b"\0") if item]
        index = 0
        while index < len(tokens):
            status = tokens[index]; index += 1
            count = 2 if status.startswith(("R", "C")) else 1
            paths = tokens[index:index + count]; index += count
            if paths:
                name_records.append((status, paths))
    else:
        for line in name_status.splitlines():
            if not line:
                continue
            parts = line.split("\t")
            name_records.append((parts[0], parts[1:]))
    changed = ["\t".join([status, *paths]) for status, paths in name_records]
    for status, paths in name_records:
        if status.startswith("R") and len(paths) >= 2:
            notices.append({"kind": "RENAMED", "from": paths[-2], "to": paths[-1]})
        elif status.startswith("D") and paths:
            skipped.append({"kind": "DELETED", "path": paths[-1], "reasonCode": "NO_NEW_SIDE_TEXT"})

    binary_paths = set(re.findall(r"(?m)^Binary files a/(.+?) and b/(.+?) differ$", diff))
    for before, after in binary_paths:
        skipped.append({"kind": "BINARY", "path": after or before, "reasonCode": "BINARY_DIFF"})
    for path in re.findall(r"(?m)^Submodule (.+?) [0-9a-f]+\.\.[0-9a-f]+", diff):
        skipped.append({"kind": "SUBMODULE", "path": path, "reasonCode": "SUBMODULE_POINTER"})

    generated_pattern = re.compile(r"(^|/)(dist|build|coverage|node_modules)/|\.(min\.js|map|lock)$", re.IGNORECASE)
    for _, paths in name_records:
        path = paths[-1]
        if generated_pattern.search(path):
            skipped.append({"kind": "GENERATED", "path": path, "reasonCode": "GENERATED_PATH_RULE"})
    numstat_lines = (numstat.decode("utf-8", errors="replace").split("\0") if isinstance(numstat, bytes) else numstat.splitlines())
    for line in numstat_lines:
        parts = line.split("\t")
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        if int(parts[0]) + int(parts[1]) > 10_000:
            skipped.append({"kind": "LARGE_FILE", "path": parts[-1], "reasonCode": "DIFF_LINE_THRESHOLD"})
    return {
        "comparison": comparison,
        "changedFiles": changed,
        "includePaths": include_paths,
        "excludePaths": exclude_paths,
        "notices": notices,
        "skipped": skipped,
    }
