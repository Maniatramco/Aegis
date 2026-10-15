# Historical design verification

These dated notes retain earlier design decisions and laptop-only evidence. The current standards are [workflow design](../ags_design/WORKFLOW-DESIGN.md) and [Agent identity](../ags_design/AGENT-BRAND.md).

# Extract list and separate Review page — 11 October 2026

final result: passed

## Grouped workspace navigation and Extract actions — 2026-10-11

Implemented Home and Aegis Agent as top-level links, Onboard with Dataset / Prompt / Extract, and Model with Model Reg / Model Mapping. Existing admin-only model permissions remain enforced. The standalone Re-extract screen is removed; legacy links redirect to Extract. Every eligible extraction row has Re-extract and Review actions. Re-extract opens options and live shared workflow progress in a dialog, creates a fresh result, and preserves the selected run and original files.

Browser verification used the real local mapped model on the fictional Alice Example benchmark fixture. Starting from reviewed extraction `65598326-0e05-494b-9786-8424cdeae9bb` (version 3), the row action produced `2e973c30-1c46-4b0f-a62c-d25d29f86228` (version 1). Review opened the new result with Alice Example / Cedar City / Python / 5 and Save disabled until edited. Returning to the previous result confirmed its reviewed version 3 and values remained intact. Canceling options before starting did not create a run.

Verified all five grouped destination links, Onboard collapse/expand, legacy #Re-extract redirect, and the mobile drawer opening and closing on navigation. At 390px viewport, page content width equals viewport width, and both row actions are accessible. The re-extraction dialog fits mobile height and its completed Review results action works. Browser console reported no warnings or errors.

Evidence: `C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/grouped-navigation-extract.png` (desktop groups and row actions), `extract-row-reextract-running.png` (real active workflow), and `extract-row-reextract-mobile.png` (mobile completed workflow). Six focused frontend checks passed; TypeScript and the deployed production web build passed; git diff whitespace checks passed.

## Sources and normalization

- List source: `C:/Users/Laya/Documents/Codex/2026-10-11/can/.codex-remote-attachments/01a12a89-7465-75b0-9df1-37b560e1397e/9ac8e65b-df51-4c4d-bb0c-d3bd038f8597/1-90558.jpg`, 1280 × 960 pixels.
- Editor source: the previously approved `.../927ec5c2-1a18-46c9-87c9-e72afc3ab5e1/1-90559.jpg`, 1280 × 960 pixels; full path retained in the earlier report below.
- Implementation evidence: `C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/extract-list-desktop-final.png` and `review-separated-desktop.png`, both 1280 × 800 PNG pixels, captured through the in-app browser's CDP capability at 1280 × 800 CSS pixels and devicePixelRatio approximately 1.
- Responsive evidence: `extract-list-mobile-final.png` and `review-separated-mobile.png`, 390 × 844 pixels/CSS viewport, same evidence folder.
- Both source photographs and both desktop implementation images were opened together in one comparison input. The photographed application regions, approximately x=235–1150/y=45–695 for the list and x=180–1200/y=45–705 for the editor, are the comparison targets. Browser chrome, keyboard, taskbar, perspective distortion, and another company's branding are excluded. This implements the user's requested two-screen pattern in the existing Aegis design system; it is not a pixel-identical copy of the photographed banking application.
- The table headers, status badges, Review actions, pane headers, field inputs, PDF toolbar/thumbnails, and footer are readable in the full-resolution comparison. Separate focused captures were not needed to judge these controls.

## Findings and comparison history

1. Initial desktop list had wrapped filters and excessive total height. Initial evidence: `extract-list-desktop.png`. Adjusted toolbar to four compact columns, reduced row metadata to two lines, shortened displayed IDs with full-ID hover text, and bounded the table scroll area. Final list has visible actions and pagination within the desktop viewport; measured page height equals viewport height (800).
2. Initial Review grew below the viewport after its context header was added. Bounded pane height relative to viewport; final desktop has two equal panes, both 477.2 × 415 CSS pixels, with the bottom Save footer visible and page height 800.
3. Initial mobile list hid document names behind metadata columns: `extract-list-mobile.png`. Final mobile prioritizes Document / extraction, Review status, and Actions; dataset remains selected through the filter. `extract-list-mobile-final.png` shows identifiable files and available Review controls. Page width 390 equals viewport width; Review page width remains at or below viewport width. On intermediate widths, the Action column stays visible while the table scrolls horizontally.

No actionable P0/P1/P2 findings remain.

## Required fidelity surfaces

- Typography: existing Aegis UI fonts and compact hierarchy retained; table copy 11–12 px and secondary metadata 9–10 px. Long dataset names truncate with full text available on hover; document identities wrap. Source is a perspective photograph, so font identity cannot be established precisely.
- Spacing: search/filter toolbar above a dense striped table; right-aligned per-row Review actions. Review has aligned field/source panes and a bottom save area. The list and editor are separate routes and visible regions.
- Colors: existing white/navy/blue Aegis surfaces and actions retained. Reviewed is green; Pending review is amber; failed processing remains distinct from review status.
- Assets: existing Aegis logo and Lucide icons reused. PDF displays the actual original document through authenticated page-image endpoints; no placeholder or fabricated source image. Reference company's logo is intentionally not adopted.
- Copy/content: application labels are Extract and Review; Dataset, Prompt template, Document / extraction, Extracted time, Review status, Actions reflect actual Aegis metadata. Trade Type / Deal Name from the reference map to Aegis's template / document identity, rather than inventing financial attributes.

## Browser interactions verified

- Extract → Review opens canonical `#Review/<extraction-id>`; the editor does not appear in the list.
- Back preserves search/column filters in the same live session; returns to Extract. Agent → Review → Back restores the same conversation and completed goal. New extraction remains available through `#Extract/create`.
- Review route survives browser reload and loads the exact extraction through the existing authorized API.
- Dataset and review-status filters, full extraction ID search, column search, empty results, Clear, sorting, and next/previous pagination verified against 70 existing runs.
- Save initially disabled; edit enables Save; Cancel restores values and disables Save. A synthetic Alice benchmark result was saved, reloaded, and its city restored to Cedar City through the UI; review status is Reviewed and version is 3. Original source text stayed unchanged. No user document values were edited.
- Unsaved navigation is blocked without discarding the draft; Cancel restores the saved value.
- Actual PDF renders (natural width 993 px), reports one page, and zoom changes from 100% to 125% then resets to 100%.
- Mobile document names and review actions visible; Save remains at the bottom and disabled when unchanged.
- Browser error logs: none in the verification tab.
- TypeScript check, production Docker web build, four directory/citation regression tests, and git diff whitespace check passed. Existing review-flow automation selectors were updated for the split routes; this turn's UI E2E verification used computer skills, not terminal Playwright.

## Follow-up polish

None required for this request. Wider tablets retain horizontal table scrolling for full metadata; mobile intentionally shows the primary columns.

---

## Earlier accepted editor design QA (retained)

# Extraction Review redesign — 11 October 2026

final result: passed

Source visual truth: `C:/Users/Laya/Documents/Codex/2026-10-11/can/.codex-remote-attachments/01a12a89-7465-75b0-9df1-37b560e1397e/927ec5c2-1a18-46c9-87c9-e72afc3ab5e1/1-90559.jpg` (1280 × 960 pixels).

Implementation: `http://localhost:3003/#Extraction%20Review`, production Docker web/API against the existing workspace. Evidence folder: `C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/`.

## Comparison evidence and normalization

- Full final screenshot: `review-desk-final-full.png`, 1264 × 811 raster pixels. Desktop viewport: 1280 × 800 CSS pixels, observed devicePixelRatio approximately 1. Full-page capture includes document height; scrollbar/capture normalization accounts for the narrower raster width. The reference is a perspective photograph, with browser chrome, Windows taskbar, and laptop keyboard. Comparison uses its application region (approximately x=180–1200, y=45–705), rather than claiming pixel equality with the photographed device.
- Reference and final screenshot were opened together in the same comparison input. Focused evidence: `review-desk-focused.png` (953 × 415), showing field density, selection, matched pane headers, original document thumbnail and toolbar. Full evidence is authoritative for the complete toolbar and surrounding navigation.
- Saved state: actual Sara Khan fictional sample extraction, version 1, with unchanged source PDF. One original page is displayed because that original contains one page. The financial fields and third-party branding from the reference are intentionally replaced by actual Aegis data and its existing identity.
- Edited state: `review-desk-edited.png` (1265 × 791), 1280 × 800 CSS viewport. Yellow modified field and enabled bottom Save are visible. This draft was cancelled without saving to that extraction.
- Tablet: `review-desk-tablet.png` (753 × 784), 768 × 800 CSS viewport. Phone: `review-desk-mobile.png` and `review-desk-mobile-document.png` (each 375 × 811), 390 × 844 CSS viewport. Also checked 662 × 668 CSS viewport. Screenshots exclude the vertical scrollbar and use browser capture normalization; screenshots were not stretched to match the source.

## Findings and comparison history

1. [P1 resolved] Existing review gave fields four times the source width and showed a large results directory above the review. The reference uses a compact selector row and balanced fields/document panes. Implemented compact dataset/extraction selectors, a browse disclosure, and equal pane tracks. Final desktop panes are balanced and the source is readable.
2. [P2 resolved, pass 1] `review-desk-desktop-pass1.png` showed the Save label wrapping and the page scrolling the workspace header out of view. Changed footer buttons to retain their intrinsic width and opened standalone reviews at the top of the page. Reduced the duplicate heading and adjusted pane height for the viewport. Post-fix: `review-desk-desktop.png`, `review-desk-final-full.png`, and edited-state evidence show a single-line Save label, visible global header, and bottom footer inside the 800px viewport (bottom=790px).
3. [P2 resolved] Save was previously above the fields. It now lives in a sticky bottom footer, remains disabled for unchanged results and invalid JSON, enables for valid edits, and disables after Cancel or successful save. Edit inputs are disabled while saving to prevent losing newer keystrokes during a request.

No actionable P0/P1/P2 findings remain.

## Required fidelity surfaces

- Typography: retained Aegis Segoe UI, Arial, system-ui fallback. Compact 11px field labels, 12px values, 13px panel headings and 16px review title match the reference's dense workstation hierarchy. Uppercase labels, sensible weights and line heights, native input scrolling, multiline long values, and wrapping field paths were inspected at desktop/tablet/phone sizes. No distorted text or missing fallback font was observed. The reference photograph does not permit an exact typeface or antialiasing measurement.
- Spacing/layout: aligned selector row and panel headings; equal columns; thin table dividers; shallow borders and small radii. Fields and source scroll independently. Mobile stacks the panes while retaining the bottom action bar. No horizontal document overflow at 1280, 768, 662, or 390 CSS pixels. Footer controls remained visible at all tested sizes.
- Colors/tokens: retained Aegis blue and white, navy text and subtle neutral borders. Selected fields use pale blue; unsaved modified values use pale yellow; saved status uses green. The original viewer uses dark neutral chrome, white original pages and a blue thumbnail selection. Disabled actions are visibly subdued and semantically disabled.
- Assets/images: existing platform logo and Lucide library controls were reused. Document and thumbnail images are rendered from actual unchanged original PDFs, with their natural aspect ratio and sharp text. No document screenshot, logo, photo, or illustration was fabricated. Zoom intentionally permits scrolling within the document canvas. TXT/DOCX retain the honest text fallback and original download.
- Copy/content: labels describe actual Aegis selections and results. Metadata/provenance remain accessible in disclosures. Evidence warnings and original-document provenance are preserved; coordinates and verified highlights are not invented. Save confirmation accurately says results change while originals remain unchanged.
- Icons/accessibility: toolbar icon buttons have accessible names; download/open icons also have titles. Fields, PDF page input, selectors and Save/Cancel are labelled native controls. Blue keyboard focus, selected row state, disabled states, and native modal focus handling were verified. Escape closes the expanded source view. No new animation or motion was introduced.

## Interaction and validation evidence

- Production frontend build, TypeScript check, and `git diff --check` passed.
- 15 backend tests passed (`test_requirements_v1.py`, `test_merged_documents.py`). Coverage includes actual PDF page counts before indexing, blank second-page rendering, out-of-range rejection, cross-owner denial, unchanged original bytes, immutable review revisions, stale-version conflict and merged-source preservation.
- Real browser: Save initially disabled; editing a fictional QA field enables Save and marks one modified row; Cancel restores the original and disables Save; invalid complete JSON blocks Save. Saved `Alice Example — review QA` in the existing isolated journey QA extraction, reloaded the application, reopened it and confirmed persistence with Save disabled. Restored `Alice Example` and saved again; review history retains both revisions. No original document was modified.
- Verified merged record-to-original navigation (second record selects the second source), profile filtering, dataset/extraction switching, actual one-page bounds, PDF zoom/reset, expand/close and Escape. Mobile export and browse menus remain within the 390px viewport. Existing export formats remain available.
- Console: browser error log returned `[]` after the verified flows. A temporary test tab encountered connection refusal during the service restart; verification continued in a fresh tab after the service was healthy. This was not an application render error.
- Residual coverage limits: available saved original PDFs were single-page; multi-page rendering/count validation was tested against a two-page backend fixture. Re-extraction and production export downloads were preserved but not rerun in this visual redesign pass.
- Cleanup: fictional QA value restored, transient Sara draft cancelled, viewport overrides cleared and temporary verification tab closed. User tab retained its original sample-resume extraction with Save disabled.

## Follow-up polish

No blocking follow-up. The source photograph's financial grouping names and brand are not part of Aegis's data model and were not copied.

---

## Historical QA — 7 October 2026

Aegis design QA — 7 October 2026

Source visual truth:
C:/Users/Laya/Downloads/backup-photos/ChatGPT Image Oct 7, 2026, 05_49_51 PM.png
Source pixels: 1672 x 941, illustrative four-screen board, no defined runtime CSS viewport/device density.
Implementation: http://127.0.0.1:3001/ against actual local storage, worker, Ollama, Nomic and offline reranker.
Screenshots live in the task outputs folder. Desktop target 1440 x 900 CSS pixels; phone 390 x 844; tablet 1024 x 768.
Desktop screenshots 1440 x 900 pixels; review full-page 1424 x 1187 (vertical scrollbar/full content). Phone captures use a 390 CSS-pixel viewport; review full-page includes vertically stacked results and PDF. Windows desktop scaling was 125%; fullPage screenshots normalized to CSS pixel dimensions, rather than comparing native cropped window pixels.

Comparison evidence:
Workflow-Design-Comparison.png places the complete source board and actual Home, Chat, failure stages and saved Review into the SAME 3344 x 1140 comparison input. Captures are proportionally fitted, not stretched, to 822 x 500 tiles. Browser chrome/canvas padding are excluded. Source and implementation contain different synthetic data: the source is fictional, while the implementation displays actual backend values/status and a real synthetic PDF.
Workflow-Review-Comparison.png provides a readable focused source Review crop (842,528)-(1660,933) beside the actual Review crop (270,275)-(1410,1150), proportionally contained in 900 x 700 and 1100 x 700 regions. The reference shows unsaved edits; Workflow-Review-Unsaved.jpg separately verifies that state, while the focused comparison shows saved version 3 and the open export menu. These are intentional documented state differences, not a pixel-exact match claim.
Workflow-Chat-Tablet-Scope.jpg verifies the ready-document selector open on a 1024px viewport; measured bounds left 576/right 996.

Findings and iteration history:
[P1 resolved] Chat dataset selection was hidden inside configuration. The reference exposes dataset selection beside the model. Fix: direct native labelled Chat dataset selector always visible in the chat context row. Post-fix real Chrome selects the synthetic dataset and displays ready-document/model options. Evidence: Workflow-Chat-Desktop-Final.jpg and Workflow-Chat-Mobile-Final.jpg.
[P2 resolved] A broad upload list CSS selector restyled nested horizontal workflow stages, causing cramped mobile labels. Fix: direct-child upload row selector. Evidence: Workflow-Stages-Desktop-Fixed.jpg and Workflow-Retry-Mobile-Fixed.jpg show four readable left-to-right stages.
[P2 resolved] Older narrow icon rail rules conflicted with the reference navy labelled navigation. Fix: shared navy/blue tokens and higher-specificity 205px labelled rail. Evidence: final desktop Home/Chat/Review.
[P2 resolved] Expanded chat navigation inherited a white panel with pale text. Fix: explicit navy background for the admin-navigation panel. Actual computed colors verified as background rgb(12,39,75), foreground rgb(228,237,249). Evidence: Workflow-Navigation-Final.jpg.
[P2 resolved] At tablet width the document selector opened beyond the right screen edge. Fix: right-anchor the popover on desktop/tablet; retain a full-context-width mobile anchor. Real measured 1024px bounds 576–996; no clipped controls. Evidence: Workflow-Chat-Tablet-Scope.jpg; unchanged CI responsive assertions.
[P2 resolved] The 320px extraction review header grew to 845px for a very long synthetic filename. Fix: min-width:0, max-width:100%, overflow-wrap:anywhere on the title region. The responsive test retains the long name and unchanged overflow assertion; exact-commit CI is recorded separately in Workflow-CI-Results.json.
[P2 resolved] The open export menu started at -30px on a 320px phone. Fix: anchor the menu to the full review action row at narrow widths. Final real Chrome bounds left 32.8/right 262.8 within a 320px viewport. Evidence: Workflow-Phone-Export-Final.jpg. Live full-page phone captures exclude a 15–16px scrollbar: 304px wide at 320 CSS pixels and 375px at 390.
[P2 resolved] Chrome's inline PDF surface remained blank on a narrow phone even when scrolled into view. Fix: at phone width show an explicit protected Open original source link and explanation, rather than the blank iframe. Desktop retains the actual PDF beside results. Real Chrome clicking the phone link rendered the original PDF in its own tab; invoice NS-1042 and 2640 USD were visible. Evidence: Workflow-Review-Mobile.jpg, Workflow-Phone-Original-PDF.jpg, final desktop Workflow-Review-Downloads.jpg.
Exact final commit 3a788f290ed2c4a727c713710f66185a40143cb8 passed all four CI jobs, including 35 browser workflows and three responsive/screenshot tests. Final downloaded CI-3a788f2/responsive/layout-audit.json contains 96 records and zero overflow findings. Authoritative snapshot: Workflow-CI-Results.json.

Five required fidelity surfaces:
Fonts/typography: familiar sans-serif system UI, heavy navy section headings, regular readable body, smaller muted metadata; 14–16px fields and chat text. The illustrative reference font is not identified; implementation preserves the existing product font stack rather than claiming an exact font match. Long content uses natural wrapping, dataset/model names use bounded selectors, and phone fields are 16px. Font rasterization differences are expected after density normalization.
Spacing/layout rhythm: white cards, restrained 6–12px radii, subtle borders, generous 18–28px padding, aligned search/table rows. Desktop review retains left results/right PDF. Phone review stacks results before source. Chat has bounded message width and a reachable composer. Extra secondary tools remain under Manage workspace because the production app has more screens than the four-item illustrative reference. Functional source viewer is larger than the fictional invoice thumbnail.
Colors/tokens: navy #071b36 navigation, blue #0667ef actions, white surfaces, #102143 text, muted #546580, subtle #dce5f1 borders. Actual green completion, amber unsaved/pending and red failure use text/labels as well as color. Expanded navigation contrast corrected. Disabled controls visibly muted.
Images/assets: supplied existing Aegis raster logo reused at natural aspect ratio; existing icon library reused consistently. No generated logo, handcrafted illustration, fake document screenshot or custom decorative SVG art. The original PDF viewer is the real backend-owned synthetic file, with Chrome's native viewer controls. The app's established logo differs slightly from the illustrative reference logo; preserving existing product branding is intentional.
Copy/content: real datasets, counts and job states replace invented reference numbers; exports explicitly state saved values only. Temporary retention is explained accurately. Local-only empty chat no longer displays paid-provider approval copy. Error text is actual backend failure. Original page fallback explicitly says region coordinates are unavailable; no source highlight is invented.

Interaction/responsive evidence:
Actual Chrome exercised dataset selection/Open chat, model switching, ready-document scope, citation evidence dialogs, horizontal stages, retry, version-preserving re-extract, hiding/reopening, review field edit/Cancel/Save/Reload, all three downloads and mobile layouts. The real backend checked stale-version conflict, schema validation/failed-write preservation, job de-duplication, temporary-only cleanup and permanent reference protection. CI covers keyboard focus, native modal dismissal, reduced motion, short landscape, 320/390/768/1024/1440/844 widths and 200% reflow/text scaling. Exact CI outcome remains authoritative in its output snapshot.
Console errors: final restored Chrome tab checked; no application errors observed during verified flows. Expected network failure during stopped-service recovery is not counted as an app render error. Existing data/accounts were preserved when services were relaunched.

Residual test gaps and intentional limits:
Visual pass is not a claim that every model answer is correct. The real SmolLM2 follow-up cited a page missing its amount; Qwen remains default and model quality is tracked in issue #14.
Local Chrome file chooser automation is awaiting explicit approval for the extension's file URL permission. Backend upload and CI file inputs are tested, but this live chooser gap is not claimed passed.
Structured field-level evidence was absent in the sample; honest associated page fallback is displayed. No OCR or fabricated coordinates. Saved reviewed values do not rewrite original indexed evidence.
Older undigested indexes need explicit reindexing. Permanent originals are retained.

Implementation checklist:
Completed: visible dataset/model controls; four horizontal stages; left/right review; saved-only exports; consistent navy/white/blue; responsive wrapping; keyboard/native dialogs; genuine source fallbacks; original preservation.
Follow-up polish [P3]: the reference board's custom fictional invoice typography differs from the real PDF; preserve original rendering. The account footer retains the existing compact placement. No pixel-exact board recreation claim.

final result: passed

---

Aegis workflow stepper QA — 11 October 2026

final result: passed

Source: ags_docs/ags_design/workflow-stepper-reference.png (780 x 540 pixels). The user then explicitly requested blue/white colors and a working-agent animation; these override the purple palette/white active dot in the image. Their request also replaces generic Step 1 labels with real workflow names. Compact 48px markers, 3px connectors, 126px minimum stage width and variable workflow length are intentional adaptations to the existing application.

Implementation: http://localhost:3003/, shared WorkflowStepper, actual authenticated local workspace. Normal desktop captures are 1280 x 720; mobile uses a 390 x 844 CSS viewport (375px content plus vertical scrollbar). The reference is a standalone visual without specified CSS viewport or density. Screenshots use browser CSS-pixel captures; no native-window scaling comparison is claimed. Comparison crops remove surrounding application content only, and retain all workflow states.

Combined comparison input opened and inspected: C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/workflow-blue-final-comparison.png. Includes the source reference and the final real desktop/mobile processing captures in the same image. Desktop/mobile captures show completed, active and pending stages; the reference has three markers while the real extraction has seven. A frame captured immediately after restoring normal motion shows the brief check appearance animation. This is a transient animation state, not a persistent color difference.

Resolved findings:
- [P2] Expanded extraction cards widened the assistant conversation at narrower widths. Fixed the grid tool card minimum width and applied inline-size containment to the shared stepper. Post-fix measured phone conversation clientWidth/scrollWidth both 362px; extraction stepper internally scrolls 882px of stages within 290px in the assistant. Actual final review stepper has a 284px viewport and centered active Extract fields stage at x=124.4, scrollLeft=299.2. Page content fits the viewport.
- [P2] The halo initially remained animated in reduced-motion mode because its active selector had higher specificity. Matched selector specificity in the motion override. Final browser emulation confirms halo, agent icon and completed check animationName all none. After reset, normal halo/agent names are workflow-agent-working/workflow-agent-bob.

No remaining P0/P1/P2 visual differences from the user-approved adaptation. The horizontal circles, completed connectors, white checkmarks, pending markers, pale blue canvas and real step labels are consistent across prompt, document, assistant-tool and extraction workflows. Running stages use a white Lucide agent icon, subtle motion and a soft blue halo. Completed checks appear briefly; failure states retain visible attention styling and error text. Marker icons are functional UI state icons, not replacement artwork.

Verification:
- 50 relevant frontend tests passed; TypeScript passed; production Docker web build passed; git diff --check passed for changed tracked frontend files.
- Real browser prompt review/confirmation saved prompt-workflow-qa.json as version 4 in the isolated QA dataset. Saved receipt remained visible; no Retry request shown for the successful save.
- Confirmed assistant upload -> indexing -> extraction -> review. Extraction c15e2f79-606b-435c-b395-9568fbaa7d12 returned owner = Prompt Workflow Example. Re-extraction versions 2, 3 and final 4 completed with the same expected value; final run used the final deployed shared component. The running agent disappears when processing finishes and the saved review result appears.
- Real completed user workflow ff940fb8-9320-4b28-a3c2-c7c80d0903c0 and its prompt receipts restore after browser reload; actual stage names retained.
- Desktop, mobile, live active/pending/completed status, keyboard focus and reduced-motion checks performed through the computer-use browser API. No timing-based fake progress.

Evidence: workflow-blue-agent-desktop-final.png, workflow-blue-agent-mobile-final.png, workflow-blue-completed-result.png, workflow-standard-tests.txt under C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs.

Scope: frontend workflow standard and animation. This pass does not repeat unrelated backend acceptance checks. Previous QA above is preserved as historical evidence.

## Aegis Agent identity and extraction-summary follow-up — 2026-10-11

- Renamed unified workspace, navigation, breadcrumb, conversation labels and composer to Aegis Agent. Verified an old #Aegis%20Assistant bookmark opens the canonical #Aegis%20Agent route and the unified workspace.
- Added a shared generated blue A/agent-face logo derived from the existing Aegis platform mark. Verified 24px navigation/replies, 28px title and 64px welcome. Production WebP is 26,412 bytes with alpha. Asset provenance and generation prompt are in ags_docs/AGENT-BRAND.md.
- Desktop and 390px mobile inspected visually; all agent images load and mobile body width equals viewport width. Viewport override reset after QA.
- Fixed current workflow lookup: read-only answer plans no longer mask executable plans. Snapshot reads current accepted job status without submitting any work. Local semantic classification receives verified reference context alongside the current request and selects the latest workflow scope for implicit extraction follow-ups.
- Replayed the exact “can you summarize” request in conversation 47993be5-24e3-4c77-86b3-88a2d16256b7 using the actual Qwen3 Chat model in the browser. Final reply summarizes Sara Khan only, says completed/version 1/unreviewed, cites saved values and links extraction ff940fb8-9320-4b28-a3c2-c7c80d0903c0. Review button opens that exact extraction and unchanged source PDF. Historical incorrect answers were preserved.
- Before/after: owner job count 110, extraction version 1 and status ready. Summary and Review did not rerun extraction.
- Validation: frontend 50 tests passed; TypeScript and production web build passed. Backend graph/application-state/chat suite passed 98 tests before the additional scope/template checks; final graph suite passed 30 tests, and 3 focused regressions passed after the final edits (current context in local templates, completed/repeated scoped summary, unconfirmed workflow summary). Installed the repository-pinned pyarrow 26.0.0 in the local test environment, which had lacked Parquet support. Production API and web rebuilt and deployed.
- Evidence: C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/aegis-agent-brand-welcome.png, aegis-agent-summary-final.png and aegis-agent-summary-review.png.
- Repeated the exact follow-up once more in the user's original tab after final deployment. Correct one-profile completed summary is now visible there, while its completed workflow cards remain intact. Screenshot: C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/aegis-agent-user-tab-final.png. Temporary QA tab closed; user tabs preserved.

## Compact live answer workflow — 2026-10-11

- Added server progress events around actual conversation/workspace reads, request classification, read-only tools, response generation and response saving. Events contain public operation labels and timing only. Final workflow snapshots are stored with the canonical reply; no guessed future stages or model reasoning are displayed.
- Added AgentAnswerWorkflow beneath replies: closed by default, current stage and elapsed time, animated blue AgentLogo during processing, expandable shared horizontal WorkflowStepper. Completed/stopped/failed states retain timings and stop animating. The display standard is documented in ags_docs/WORKFLOW-DESIGN.md.
- Browser tested with actual Qwen3 Chat in conversation a1d8bd30-0bfb-4173-a475-840b7ef2f2fa: observed Understanding request at 5s and 9s, then Generating response; final completed stages show classification 33s, generation 5s, total 39s. Reload restored the same timings and a closed disclosure. Completed logo animation is none.
- Replayed can you summarize in the user's original conversation 47993be5-24e3-4c77-86b3-88a2d16256b7. Observed real classification, Checking saved extractions and Reading saved fields; completed total 19s. Answer still identifies Sara Khan, completed/version 1/unreviewed and extraction ff940fb8-9320-4b28-a3c2-c7c80d0903c0. Saved summary performs no model-generation stage or extraction action.
- At 390px the page body width equals the viewport. Expanded six-stage list scrolls internally (756px content inside 316px container); compact row and timing fit. Restored normal browser viewport and left the original user tab showing the completed compact workflow.
- Browser Stop test froze the current response at 11s, displayed Response stopped, removed active animation and preserved earlier completed reply. Frontend integration tests cover progress/delta interleaving, completed timing retention and stop/cancellation freezing; backend tests cover actual stage events, canonical persistence and terminal failures.
- Validation: 44 backend streaming/graph tests passed, plus the focused saved-summary progress regression; 56 frontend attachment/stream/workflow tests passed. Production API/web builds passed including TypeScript; rebuilt and deployed locally.
- Evidence in C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs: aegis-answer-workflow-active.png, aegis-answer-workflow-expanded-active.png, aegis-answer-workflow-generating.png, aegis-answer-workflow-complete.png, aegis-answer-status-active.png, aegis-answer-status-final.png, aegis-answer-status-mobile-expanded.png, aegis-answer-status-mobile-compact.png and aegis-answer-workflow-stopped.png.

## Source-aware LangGraph chat and metadata tools — 2026-10-11

- Added authorized dataset/document/prompt catalogs, dataset/job status, model-role mappings and built-in application guidance as read-only chat tools. Document metadata includes files without saved extraction results. Catalogs paginate and respect explicit document filters and dataset permissions.
- The semantic classifier distinguishes metadata and application guidance from original passages and saved fields. Supplementary content sources are explicit; the graph requires their reads and unfinished catalog/profile pages before accepting an answer. Inconsistent operation/scope or a result filter without a predicate gets one classification repair before any result read.
- LangGraph calls the chat agent to choose tools, dispatches validated arguments and returns actual observations for subsequent decisions. Mutation-proposal contracts are unavailable to metadata/help turns. Canonical replies retain request_route decisions and tool_trace; the existing compact answer workflow displays real operation labels/timings.
- Real Qwen3 Chat browser QA exposed context overflow from repeated catalogs/status reads, unrelated tool schemas, blanket mixed-source prefetch and reserving final-answer tokens for short tool decisions. Fixed these with current-question-only metadata/help turns, compact status telemetry, completed-read removal, named extraction filtering, mandatory cross-source reads, schema-free final combined composition and actual 256-token required-tool budgeting. Registered model context remains 8,192 tokens.
- Replayed the exact typo question in original conversation 47993be5-24e3-4c77-86b3-88a2d16256b7 on the final deployment: metadata route, list_documents, all five actual Arjun_Sample filenames, no saved-result filtering. Final reply is visible in the original user tab; historical replies are retained.
- Browser QA conversation 93a3e128-73c9-46d6-9a22-af08680eb46b: dataset status reports five indexed documents and zero active jobs; model/prompt question reads mapped Qwen3 Chat, Qwen3 Extraction and Nomic Embedding defaults and four saved prompt filenames/versions.
- Combined count/saved-name query selects metadata with supplementary results, calls get_dataset_status, find_extractions(name=sarakhan-extraction), then read_extraction_results(fields=[full_name]). Final answer is five documents and Sara Khan, with saved citation and Review link to ff940fb8-9320-4b28-a3c2-c7c80d0903c0. Final composition retains actual observations and omits repeated tool schemas.
- Original-PDF degree question selects documents, calls search_documents scoped to 04-sara-khan-frontend.pdf and answers B.Tech in Information Technology from the original page-1 passage with its citation. A saved-summary follow-up selects results and returns Sara Khan only, completed/version 1/unreviewed, with the same extraction Review link.
- Final application-help question selects application and uses built-in guidance to describe Extraction Review, dataset/result selection, source comparison, edits and Save changes. Developer/API entries are opt-in; normal product guidance uses UI controls.
- Before/after owner job count remains 110; Sara extraction remains ready/version 1. No upload, extraction, re-extraction, configuration or permission change was executed during these production read checks. Only API was rebuilt/deployed; frontend workflow/brand standard is unchanged.
- Automated validation: 54 graph/metadata/stream tests passed before the additional saved-profile pagination regression; final 11 metadata tests passed including that regression. The Ollama/stream suite passed 45 tests with one optional skip. Together these cover 55 distinct agent regressions and 32 additional Ollama checks. A pre-existing trailing blank line in local/ags_scripts/start-oracle.ps1 is outside this change.
- Evidence under C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs: aegis-metadata-documents-final.png, aegis-agent-combined-sources.png, aegis-agent-original-document-source.png, aegis-agent-saved-summary-regression.png, aegis-agent-application-guidance.png and aegis-agent-source-routing-e2e.json. JSON records actual routes, tool arguments, source references, five document records and unchanged job/extraction checks. Temporary QA browser tab closed; user tabs preserved.

## Compact data journey and whole-workflow restart - 2026-10-11

Source truth: user-supplied `C:/Users/Laya/Downloads/backup-photos/aegis_data_journey_v2.html`, saved as `ags_docs/ags_design/aegis-data-journey-reference.html`; earlier visual `ags_docs/ags_design/workflow-stepper-reference.png` (780 x 540) supplies the approved horizontal check/active/pending structure. The latest HTML specifies navy rotating rings, incoming-only particles, Document / Knowledge / AI Chat, and completed blue tracks. The supplied HTML was read as a specification; file-protocol navigation is unavailable in the in-app browser, so its demo was not executed. This updates the existing production component rather than recreating the standalone demo page. The earlier visual and final active screenshot were opened together for comparison; newer HTML colors, sizing and marker shapes intentionally supersede that earlier mock.

Rendered evidence (all screenshots at CSS pixel density 1):
- Desktop live: `C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/aegis-compact-workflow-active-final.png`, 1280 x 720. Real Understanding request stage, rotating dark-blue ring and incoming particle flow. Component 665 x 124 px including real timings.
- Knowledge processing: `C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/aegis-compact-knowledge-live.png`, 1280 x 720. DOM inspection confirmed Knowledge active, Document completed, incoming particle animation, and the Knowledge-to-AI-Chat connector pending with animation none. This first capture exposed the duplicate global progress finding below.
- Failure: `C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/aegis-compact-workflow-failure.png`, 1280 x 720. Document completed / Knowledge failed / AI Chat pending, restart action present; every particle has animation none, no active ring. Journey 665 x 105 px.
- Completed: `C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/aegis-compact-workflow-completed.png`, 1280 x 720. Three white checkmarks on blue markers, two solid blue connections, retained original and completed saved Alice Example extraction.
- Mobile: `C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/aegis-compact-workflow-mobile.png`, 390 x 668. Journey 290 x 95 px, 32px markers, horizontal keyboard focus; page scrollWidth equals 390 and journey scrollWidth equals 290. All three labels and statuses fit.
- Short screen: `C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/aegis-compact-workflow-short-screen.png`, 900 x 500. Journey 665 x 92 px, 32px markers; page scrollWidth equals 900.
- Final downstream chat: `C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/aegis-workflow-restart-chat-verified.png`. Saved-result chat answers Alice Example with the new extraction citation.
- Canonical worker/agent evidence: `C:/Users/Laya/Documents/Codex/2026-10-11/can/outputs/aegis-compact-workflow-e2e.json`.

Fidelity surfaces:
- Typography: existing Aegis font retained; compact 11px actual names and 10px secondary statuses, wrapping permitted for long operation names. No generic step numbers replace operation names.
- Spacing: 38px markers, 32px at narrow/short breakpoints, 2px connector, maximum 665px; three-stage journey fits mobile without scrolling. Longer extraction/answer phases retain internal scrolling and active-stage focus.
- Colors: #0b316f / #123c8c active ring; #2563eb completed markers; #2a62b4 completed connectors; #c8d6e9 pending connectors; #f6f9fe canvas. Failure preserves accessible red attention state.
- Assets: existing Aegis brand retained; Lucide FileText, List, MessageCircle and Bot are real library icons. No new raster asset is needed for this functional UI.
- Copy/content: Document groups real upload and read stages; Knowledge uses actual indexing state; AI Chat uses actual readiness. Failure/retry text describes retained originals and earlier results. Counts and timings remain server-derived.

Comparison history and findings:
1. [P2, fixed] Duplicate background journey covered the foreground Knowledge stage during restart. Root cause: OperationProgress excluded owned jobs from its job list but still included upload batch rows for the same owned job. Both inputs now honor foreground ownership. Meaningful regression checks assert no background popup for ten owned upload rows, while unrelated jobs remain visible. Final browser active and completed captures have no duplicate popup.
2. No remaining P0/P1/P2 layout or behavioral findings. Reference has no failure state; failure attention color and full restart controls extend the existing product pattern. Earlier purple/circle-only mock differs intentionally because the latest user HTML updates the design.

Interactions/verification:
- Real Qwen3 agent proposed upload + extraction; browser confirmed fictional file and saved prompt in an isolated QA dataset.
- A QA-only 32-token embedding context generated a real worker failure. Animations stopped, AI Chat remained pending, and Restart workflow became available.
- Corrected only QA embedding settings; browser restart reread original and rebuilt knowledge. A separate extraction context failure also stopped the run. Corrected only QA extraction settings and restarted again.
- Final attempt completed all index and extraction phases and saved `{full_name: Alice Example}`. One retained original, document version 3, two retained earlier failed extraction records, two archived workflow attempts. Retained original SHA256 matches the uploaded fixture exactly.
- Asking AI Chat for full_name used results routing, find_extractions and read_extraction_results and cited the successful result. It did not rerun processing.
- Completed state survives browser reload. Reduced-motion emulation returns animation none for the active ring, and animation none / display none for all flowing particles. Clearing emulation restores workflow-ring and workflow-particle. Temporary viewport/media overrides reset.
- Browser console: no errors in final checks.
- 67 frontend checks and 55 backend checks passed (122 total), TypeScript passed, production frontend/API/worker builds passed and deployed to localhost:3003. Focused diff checks passed.

Implementation checklist: shared stepper applied; true stage mapping applied; whole restart retains previous results and current settings; duplicate popup fixed; responsive/reduced-motion verified; original user data not rerun. No remaining follow-up polish required for this scoped change.

final result: passed
