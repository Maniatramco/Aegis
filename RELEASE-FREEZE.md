# Aegis source freeze 15 October 2026

Prepared for Swamy. Freeze tag: `aegis-freeze-2026-10-15`. Source branch: `python`. The parent source revision is `c05fe27`; the freeze includes the existing local application changes and the engineering handover prepared before committing.

## Deployment boundary

This is a source and documentation release. The running installation is preserved. No application deployment, registry push, restart, scaling, configuration apply, infrastructure provisioning, account operation or live document processing is performed for this handover.

The immutable tag identifies this source snapshot. It does not assert that the existing deployed container image is a byte-for-byte build of this commit. [The current OCI resource inventory](OCI-LIVE-RESOURCES.md) contains verified image and runtime observations. A future deployment needs a separately authorized release and its own image digests and receipt.

## Contents

- Existing backend changes: bounded OCI JSON object caching, scoped job polling, account deletion and updated application guidance.
- Existing UI changes: shared accessible icon actions, workflow progress, workspace navigation, onboarding, prompt tables, connection status, Review and related assets.
- OCI pilot helpers and operating guides, plus a destination-parameterized script for updating already prepared application workloads.
- Manager README, architecture PNG and editable SVG, end to end architecture guide, exact declared technology versions, deployment/onboarding guide, reusable maintainer skill and 11-page Word handover.
- `RELEASE-MANIFEST.json` fingerprints the source inputs using the algorithm recorded in that file. The Git tag identifies the complete documentation and binary handover snapshot.

## Validation

| Check | Result |
| --- | --- |
| Complete backend regression run | 1062 passed, 5 skipped, 1 API documentation catalog mismatch in 921.74 seconds |
| API documentation after correction | Both tests passed on rerun; all six missing descriptions now match the live route registry |
| Frontend unit suite | 178 passed, 0 failed |
| TypeScript checking | Passed |
| Next.js production build | Passed after the final Review accessibility change |
| OKE runtime configuration preview | Validated the OCI profile and 49 managed settings; `applied: false` |
| Deployment PowerShell script | Parser syntax check passed; script was not executed |
| Maintainer skill | Skill Creator validator passed |
| Word handover | 11 pages rendered with Microsoft Word and every page visually inspected; title styling, diagram labels and command wrapping corrected |
| Repository checks | Staged diff whitespace check passed; handover links resolve; credential-pattern and UTF-8 scan has no findings |
| Source and deliverables | All 481 source hashes and aggregate verified; repository-staged Word/PNG bytes match the supplied outputs |

The full backend process loaded the catalog before its descriptions were corrected. Its sole failure was then fixed and the complete two-test documentation module passed separately. The entire 15-minute backend suite was not repeated after this descriptions-only correction. Five opt-in integration checks were skipped; no fresh live cloud deployment, real-model benchmark, Compose/browser run or restore drill is claimed.

GitHub Actions currently triggers on `main` pushes and pull requests. Pushing this source snapshot directly to `python` does not itself establish a new CI result or deploy the application.

Local validation used Python 3.12.8 and Node.js 24.19.0 with installed Next.js 15.5.27. The frontend Dockerfile targets Node 22 Alpine; no new Docker image build or container-runtime verification is claimed by this freeze.

## Corrections made while preparing the freeze

Older lightweight UI test harnesses did not load the newer shared ActionButton component or locate actions by accessible name. They now load the real component and retain checks for confirmation, duplicate submission, consent, recovery and saved results. Prompt-table assertions reflect the current table UI. Review retains result identity in its accessible heading.

The API documentation catalog was missing six newer routes: runtime configuration, dataset deletion and restore, extraction rerun and user deletion. Their descriptions are now included; endpoint execution behavior is unchanged.

Session-only design notes, runtime evidence, credentials, environment files and deployment receipts remain outside the commit. An offline pattern scan is a release check, not a certification that every possible secret format has been detected.

## Reproduce the snapshot

```sh
git clone --branch python https://github.com/Maniatramco/Aegis.git
cd Aegis
git checkout aegis-freeze-2026-10-15
```

Follow [deployment and onboarding](DEPLOYMENT.md) for a separate environment or a future application release. Read [the maintainer skill](.agents/skills/aegis-release/SKILL.md) before changing the application contracts.


## Live architecture documentation update

On 15 October 2026 at 22:26 IST, the architecture, technology inventory, diagram and Word handover were revised on `ags_sprint1` using live read-only OCI and application inspection. The updated handover focuses on OCI resources and current Gemini mappings, with stopped laptop models identified separately. The original freeze tag and application source hashes remain unchanged. See [live resource evidence](OCI-LIVE-RESOURCES.md).


## Root handover cleanup

The current Word document, architecture, deployment guide, running technology inventory, OCI resource record, source manifest and diagram now live at the repository root. Eight superseded planning, deployment-journal and earlier agent-architecture files were removed from the active branch. Current operational runbooks, test fixtures and dated verification evidence are retained. Historical report links to retired guides point to the preserved freeze tag. Application source and the deployed installation are unchanged.
