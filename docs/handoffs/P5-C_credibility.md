BUCKET: P5-C
STATUS: COMPLETE (artifacts committed; submissions are operator work)

PROVIDES:
- `CITATION.cff` (GitHub→Zenodo DOI bridge on release tagging).
- `docs/ascl_entry.md` (submission-ready ASCL text).
- `docs/joss/paper.md` + `paper.bib` (JOSS draft + references).
- Each file states what remains operator work (accounts, buttons,
  review); nothing here pretends a submission happened.

CONSUMED BY:
- Release process (tag → DOI → ASCL → JOSS review)

FILES OF INTEREST:
- CITATION.cff, docs/ascl_entry.md, docs/joss/paper.md, docs/joss/paper.bib

KNOWN CONSTRAINTS:
- JOSS needs a public history + completed feature set; this draft
  starts the checklist, it does not finish review.
- Zenodo DOI mints on first GitHub release tag, not before.

NEXT REQUIRED ACTION:
- Tag a release; submit ASCL; open JOSS. Then final full gate.
