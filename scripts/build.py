#!/usr/bin/env python3
"""Build the cwhash profile from cwhash.yaml.

    To change the profile, edit cwhash.yaml.
    README.md, cwhash.json, resume.pdf and status.json are generated: don't edit them.

Pipeline: yamllint -> JSON Schema -> merge spec + status.json -> README.md, cwhash.json, resume.pdf

Usage:
    python scripts/build.py           # validate and regenerate everything
    python scripts/build.py --check   # validate; fail if README.md or cwhash.json is stale (CI)
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import jinja2
import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = ROOT / "cwhash.yaml"
SCHEMA_FILE = ROOT / "schema.json"
STATUS_FILE = ROOT / "status.json"
TEMPLATES = ROOT / "templates"
README_FILE = ROOT / "README.md"
JSON_FILE = ROOT / "cwhash.json"
PDF_FILE = ROOT / "resume.pdf"

# Order here is the order status fields appear in the outputs.
DEFAULT_STATUS = {
    "phase": "Pending",
    "observedGeneration": 0,
    "lastUpdated": None,
    "publicRepos": 0,
}
# Fields kept out of the README code block (contact is shown as links below it).
README_HIDDEN_SPEC = ("displayName", "contact")
# Lists rendered inline as [a, b, c] in the README.
FLOW_LISTS = ("openTo",)

PERIOD_RE = re.compile(r"^(?P<title>.+) @ (?P<org>.+) \((?P<start>\d{4})–(?P<end>\d{4}|now)\)$")
DATED_RE = re.compile(r"^(?P<text>.+) \((?P<year>\d{4})\)$")


class BuildError(Exception):
    pass


# ---------------------------------------------------------------- validation


def lint() -> None:
    targets = [SPEC_FILE, *sorted((ROOT / ".github" / "workflows").glob("*.yml"))]
    result = subprocess.run(
        [sys.executable, "-m", "yamllint", "--strict", "-c", str(ROOT / ".yamllint.yaml"),
         *map(str, targets)],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        raise BuildError("yamllint failed:\n" + (result.stdout + result.stderr).rstrip())


def load_spec() -> dict:
    with SPEC_FILE.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
    )
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(map(str, e.absolute_path)))
    if errors:
        lines = [f"  {_path(e.absolute_path)}: {e.message}" for e in errors]
        raise BuildError(f"{SPEC_FILE.name} does not match {SCHEMA_FILE.name}:\n" + "\n".join(lines))

    # Checks JSON Schema can't express.
    this_year = dt.date.today().year
    for key in ("education", "experience"):
        for i, item in enumerate(doc["spec"][key]):
            m = PERIOD_RE.match(item)
            start, end = int(m["start"]), m["end"]
            if start > this_year:
                raise BuildError(f"spec.{key}[{i}]: start year {start} is in the future")
            if end != "now" and int(end) < start:
                raise BuildError(f"spec.{key}[{i}]: ends ({end}) before it starts ({start})")
    return doc


def load_status() -> dict:
    status = dict(DEFAULT_STATUS)
    if STATUS_FILE.exists():
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        unknown = set(data) - set(DEFAULT_STATUS)
        if unknown:
            raise BuildError(f"{STATUS_FILE.name}: unknown fields {sorted(unknown)}")
        status.update(data)
    return status


def _path(parts) -> str:
    out = ""
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else p)
    return out or "(root)"


# ---------------------------------------------------------------- rendering


class _FlowList(list):
    """A list dumped inline: [a, b, c]."""


class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        # Indent block sequences under their key ("  - item"), like the hand-written file.
        return super().increase_indent(flow, False)


_Dumper.add_representer(
    _FlowList, lambda d, v: d.represent_sequence("tag:yaml.org,2002:seq", v, flow_style=True)
)


def merge(doc: dict, status: dict) -> dict:
    return {**doc, "status": status}


def render_manifest(full: dict) -> str:
    view = copy.deepcopy(full)
    spec = view["spec"]
    for key in README_HIDDEN_SPEC:
        spec.pop(key, None)
    for key in FLOW_LISTS:
        spec[key] = _FlowList(spec[key])
    spec["stack"] = {k: _FlowList(v) for k, v in spec["stack"].items()}
    if view["status"]["lastUpdated"]:
        view["status"]["lastUpdated"] = dt.date.fromisoformat(view["status"]["lastUpdated"])

    text = yaml.dump(view, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=1000)

    # The README must stay machine-readable: parse it back and compare.
    if json.dumps(yaml.safe_load(text), default=str) != json.dumps(view, default=str):
        raise BuildError("internal error: README YAML does not round-trip")
    return text


def render_readme(full: dict) -> str:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATES),
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
        autoescape=False,
    )
    return env.get_template("README.md.j2").render(
        manifest=render_manifest(full), contact=full["spec"]["contact"]
    )


def render_json(full: dict) -> str:
    return json.dumps(full, indent=2, ensure_ascii=False) + "\n"


def resume_data(full: dict) -> dict:
    """Pre-split entries so the Typst template only does layout."""
    spec = full["spec"]

    def period(item: str) -> dict:
        m = PERIOD_RE.match(item)
        end = "Present" if m["end"] == "now" else m["end"]
        return {"title": m["title"], "org": m["org"], "when": f"{m['start']}–{end}"}

    def award(item: str) -> dict:
        m = DATED_RE.match(item)
        title, _, org = m["text"].rpartition(" @ ")
        return {"title": title or org, "org": org if title else "", "when": m["year"]}

    def label(key: str) -> str:
        return " / ".join(p.upper() if len(p) <= 2 else p.capitalize() for p in key.split("_"))

    linkedin = spec["contact"]["linkedin"]
    return {
        "name": spec["displayName"],
        "email": spec["contact"]["email"],
        "linkedin": linkedin,
        "linkedinText": re.sub(r"^https://(www\.)?|/$", "", linkedin),
        "openTo": spec["openTo"],
        "education": [period(x) for x in spec["education"]],
        "experience": [period(x) for x in spec["experience"]],
        "capstone": spec["capstone"],
        "awards": [award(x) for x in spec["awards"]],
        "stack": [{"label": label(k), "items": v} for k, v in spec["stack"].items()],
    }


def render_pdf(full: dict) -> bytes:
    import typst  # imported lazily: --check doesn't need it

    return typst.compile(
        str(TEMPLATES / "resume.typ"),
        root=str(ROOT),
        sys_inputs={"data": json.dumps(resume_data(full), ensure_ascii=False)},
        ignore_system_fonts=True,  # same embedded fonts on every machine -> same PDF
    )


# ---------------------------------------------------------------- main


def write_if_changed(path: Path, content: str | bytes) -> None:
    data = content.encode("utf-8") if isinstance(content, str) else content
    if path.exists() and path.read_bytes() == data:
        print(f"  unchanged  {path.name}")
        return
    path.write_bytes(data)
    print(f"  wrote      {path.name}")


def check(path: Path, expected: str) -> bool:
    actual = path.read_text(encoding="utf-8") if path.exists() else ""
    if actual == expected:
        print(f"  ok         {path.name}")
        return True
    print(f"  STALE      {path.name}")
    sys.stdout.writelines(difflib.unified_diff(
        actual.splitlines(keepends=True), expected.splitlines(keepends=True),
        f"{path.name} (in repo)", f"{path.name} (expected)",
    ))
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="validate and verify generated files are up to date; write nothing")
    args = parser.parse_args()

    try:
        lint()
        print("yamllint     ok")
        doc = load_spec()
        print("schema       ok")
        full = merge(doc, load_status())
        readme, js = render_readme(full), render_json(full)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.check:
        ok = check(README_FILE, readme) & check(JSON_FILE, js)
        if not ok:
            print("\nGenerated files are stale. Run `python scripts/build.py` and commit the result.",
                  file=sys.stderr)
        return 0 if ok else 1

    write_if_changed(README_FILE, readme)
    write_if_changed(JSON_FILE, js)
    write_if_changed(PDF_FILE, render_pdf(full))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    sys.exit(main())
