#!/usr/bin/env python3
"""Compare IAB_Vast_ErrorCodes_EN.json against the published IAB VAST spec.

Reads the error code table from the IAB Tech Lab spec repository and reports any
drift, plus any newer spec version that has left draft status. Exits non-zero
when something needs attention, including when the check itself breaks — a
silent pass on a broken parser is the failure mode this guards against.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SPEC_REPO = "InteractiveAdvertisingBureau/VAST4.x"
TRACKED = (4, 3)
CODES_FILE = Path(__file__).resolve().parent.parent / "IAB_Vast_ErrorCodes_EN.json"
DRAFT_MARKER = "Publication Date TBD"


def api(path: str, accept: str = "application/vnd.github+json") -> bytes:
    headers = {"Accept": accept}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"https://api.github.com/repos/{SPEC_REPO}/{path}", headers=headers)
    return urllib.request.urlopen(req, timeout=60).read()


def spec_file(name: str) -> str:
    body = api(f"contents/{name}", "application/vnd.github.raw").decode("utf-8")
    if not body.strip():
        raise ValueError(f"{name} came back empty")
    return body


def spec_codes(markdown: str) -> dict[str, str]:
    lines = markdown.splitlines()
    start = next(i for i, l in enumerate(lines) if "VAST Error Codes Table" in l)
    codes: dict[str, str] = {}
    for line in lines[start + 1:]:
        row = re.match(r"\|\s*(\d{3})\s*\|\s*(.*?)\s*\|\s*$", line)
        if row:
            codes[row.group(1)] = row.group(2)
        elif codes and not line.startswith("|"):
            break
    return codes


def version(name: str) -> tuple[int, ...]:
    return tuple(int(p) for p in name.removesuffix(".md").split("."))


def published_newer() -> list[str]:
    names = [e["name"] for e in json.loads(api("contents")) if re.fullmatch(r"\d+\.\d+\.md", e["name"])]
    out = []
    for name in sorted(names):
        if version(name) > TRACKED and DRAFT_MARKER not in spec_file(name)[:2000]:
            out.append(name.removesuffix(".md"))
    return out


def main() -> int:
    tracked = ".".join(map(str, TRACKED))
    report: list[str] = []

    try:
        local = json.loads(CODES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"## Unreadable error code file\n\n```\n{exc!r}\n```")
        return 1

    malformed = sorted(k for k in local if not re.fullmatch(r"\d{3}", k))
    empty = sorted(k for k, v in local.items() if not isinstance(v, str) or not v.strip())
    if malformed or empty:
        print("## Malformed error code file\n")
        if malformed:
            print(f"- Keys that are not a 3-digit code: {', '.join(malformed)}")
        if empty:
            print(f"- Empty or non-string descriptions: {', '.join(empty)}")
        return 1

    try:
        spec = spec_codes(spec_file(f"{tracked}.md"))
    except (urllib.error.URLError, StopIteration, ValueError, KeyError, OSError) as exc:
        print(f"## Spec watch is broken\n\nCould not read the VAST {tracked} error code table "
              f"from `{SPEC_REPO}`.\n\n```\n{exc!r}\n```")
        return 1

    if len(spec) < 30:
        print(f"## Spec watch is broken\n\nOnly parsed {len(spec)} codes from `{SPEC_REPO}` "
              f"`{tracked}.md`; the table layout changed and the parser needs fixing.")
        return 1

    for code in sorted(set(spec) - set(local)):
        report.append(f"- `{code}` missing from the JSON: {spec[code]}")
    for code in sorted(set(local) - set(spec)):
        report.append(f"- `{code}` is in the JSON but not in the spec: {local[code]}")
    for code in sorted(set(spec) & set(local)):
        if " ".join(spec[code].split()) != " ".join(local[code].split()):
            report.append(f"- `{code}` wording differs\n  - spec: {spec[code]}\n  - json: {local[code]}")

    try:
        newer = published_newer()
        if newer:
            report.append(f"- VAST {', '.join(newer)} is published and no longer a draft "
                          f"(this repo tracks {tracked}): https://github.com/{SPEC_REPO}")
    except (urllib.error.URLError, ValueError, KeyError, OSError) as exc:
        print(f"Warning: could not check {SPEC_REPO} for newer versions: {exc!r}", file=sys.stderr)

    if report:
        print(f"## VAST spec drift\n\n{len(spec)} codes in VAST {tracked}, {len(local)} in the JSON.\n")
        print("\n".join(report))
        return 1

    print(f"Up to date with VAST {tracked}: {len(spec)} codes match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
