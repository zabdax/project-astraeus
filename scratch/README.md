# scratch/

Ad-hoc and one-shot scripts and their data outputs. Moved here by **bucket 7** (chore/root-hygiene) from the repo root, where they were masquerading as project files. None of them is imported by the live product tree (`app.py`, `route.py`, `astraeus/`, `ui/`, `tests/`, `runs/`).

## What's here

| File | Origin | Why it's in scratch/ |
|---|---|---|
| `extract.py` | root | One-off parser that reads an external `.system_generated` log and writes the three JSON/TXT files below. |
| `extracted_output.txt` (3.12 MB) | root | Output of `extract.py`. Regenerable. |
| `extracted_utf8.txt` (1.56 MB) | root | Output of `extract.py`. Regenerable. |
| `final_payload.json` | root | Output of `extract.py`. Regenerable. |
| `find_cycles.py` | root | AST-based circular-dependency scanner that hard-codes a path in `d:\GITHUB\OP\...` — i.e. not this repo. Wrong-path dev tool. |
| `init_project.py` | root | Original project-tree scaffold script. Superseded by the real tree. |
| `scratch_batman.py` | root | batman-package smoke test that prints at import time. |

## How to use

Most of these are kept for **historical reference only** and should not be run as part of the project. If you need to regenerate any of the data files, re-run `extract.py` against the same external log (path is hard-coded; may need updating for current machines).

## See also

- `reports/bucket7_hygiene_audit.md` — full audit, file-by-file rationale, import analysis.
- `reports/bucket7_summary.md` — what changed, what was tested, what remains uncertain.
