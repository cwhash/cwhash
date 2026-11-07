# Editing this profile

**To change anything, edit `cwhash.yaml`.** Everything else is derived from it:

| File | Made by | Edit by hand? |
| --- | --- | --- |
| `cwhash.yaml` | you (the `spec`) | yes |
| `status.json` | `scripts/status.py` in the `regenerate` workflow | no |
| `README.md`, `cwhash.json`, `resume.pdf` | `scripts/build.py` | no |

After editing, regenerate and commit the outputs together:

```bash
pip install -r requirements.txt
python scripts/build.py
```

CI runs `python scripts/build.py --check`, which fails if `cwhash.yaml` is invalid
or `README.md` / `cwhash.json` are out of date. After a push to `main`, the
`regenerate` workflow refreshes `status.json` and rebuilds the outputs.
