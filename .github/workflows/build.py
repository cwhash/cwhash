#!/usr/bin/env python3
"""Generate README.md from cwhash.yaml.

    To change the profile, edit cwhash.yaml. README.md is generated: don't edit it.
    On every push to main, build.yml runs this and commits the new README.

Steps: yamllint -> JSON Schema (schema.json) -> README.md

Usage:
    python .github/workflows/build.py           # validate and write README.md
    python .github/workflows/build.py --check   # validate only, write nothing (pull requests)
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import re
import sys
from pathlib import Path

import jsonschema
import yaml
from yamllint import linter
from yamllint.config import YamlLintConfig

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SPEC_FILE = ROOT / "cwhash.yaml"
README_FILE = ROOT / "README.md"
WORKFLOW_FILE = HERE / "build.yml"

README_TEMPLATE = """\
<!-- generated from cwhash.yaml by .github/workflows/build.py — edit cwhash.yaml, not this file -->
<!-- hey, you're reading the source. you're my kind of person. -->
```yaml
# cwhash.yaml
{yaml}```
"""

YAMLLINT_CONFIG = """
extends: default
rules:
  line-length: {max: 120}   # company names run past 80
  document-start: disable   # single-document files, no leading ---
  truthy: {check-keys: false}  # GitHub Actions' "on:" key
  new-lines: disable        # Windows checkouts may use CRLF
"""

# Lists rendered inline as [a, b, c].
FLOW_LISTS = ("openTo",)
PERIOD_RE = re.compile(r"^(?P<title>.+) @ (?P<org>.+) \((?P<start>\d{4})–(?P<end>\d{4}|now)\)$")


class BuildError(Exception):
    pass


def lint() -> None:
    conf = YamlLintConfig(YAMLLINT_CONFIG)
    problems = []
    for path in (SPEC_FILE, WORKFLOW_FILE):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        problems += [f"  {rel}:{p.line}:{p.column}: {p.desc} ({p.rule})"
                     for p in linter.run(text, conf, str(path))]
    if problems:
        raise BuildError("yamllint failed:\n" + "\n".join(problems))


def load_spec() -> dict:
    doc = yaml.safe_load(SPEC_FILE.read_text(encoding="utf-8"))
    schema = json.loads((HERE / "schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
    )
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(map(str, e.absolute_path)))
    if errors:
        lines = [f"  {_path(e.absolute_path)}: {e.message}" for e in errors]
        raise BuildError("cwhash.yaml does not match schema.json:\n" + "\n".join(lines))

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


def _path(parts) -> str:
    out = ""
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else p)
    return out or "(root)"


class _FlowList(list):
    """A list dumped inline: [a, b, c]."""


class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        # Indent block sequences under their key ("  - item").
        return super().increase_indent(flow, False)


_Dumper.add_representer(
    _FlowList, lambda d, v: d.represent_sequence("tag:yaml.org,2002:seq", v, flow_style=True)
)


def render_readme(doc: dict) -> str:
    """The README view: spec only, with name and email up front."""
    spec = copy.deepcopy(doc["spec"])
    view = {"name": spec.pop("displayName"), "email": spec.pop("contact")["email"], **spec}
    for key in FLOW_LISTS:
        view[key] = _FlowList(view[key])
    view["stack"] = {k: _FlowList(v) for k, v in view["stack"].items()}

    text = yaml.dump(view, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=1000)
    # The README must stay machine-readable: parse it back and compare.
    if yaml.safe_load(text) != view:
        raise BuildError("internal error: README YAML does not round-trip")
    return README_TEMPLATE.format(yaml=text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="validate only; write nothing")
    args = parser.parse_args()

    try:
        lint()
        print("yamllint  ok")
        doc = load_spec()
        print("schema    ok")
        readme = render_readme(doc)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.check:
        return 0
    data = readme.encode("utf-8")  # always LF
    if README_FILE.exists() and README_FILE.read_bytes().replace(b"\r\n", b"\n") == data:
        print("README.md unchanged")
    else:
        README_FILE.write_bytes(data)
        print("README.md written")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    sys.exit(main())
