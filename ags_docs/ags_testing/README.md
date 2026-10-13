# Historical verification records

This folder contains dated test reports and fictional fixtures. Reports document
the revision, environment and scope tested then; they do not replace current CI.

Manual executables moved to [manual QA tools](../../ags_scripts/ags_qa/README.md). Generated
evidence in the original `docs/testing/results/` remains locally and is ignored by Git. Existing links work
on the original laptop; fresh clones should use CI artifacts or rerun appropriate
authorized verification. Runtime uploads, database contents and secrets are
unaffected by this repository cleanup.

Generated screenshots and JSON reports previously committed directly in this
folder were removed from active source and retained locally under
`ags_runtime/ags_archive/ags_cleanup_2026_10_14/`. Updated evidence links resolve
on the original laptop; Git history retains the earlier committed copies.
Narrative reports and reusable fictional test inputs remain in the repository.
