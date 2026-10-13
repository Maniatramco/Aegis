# Saved-result answers, citations and Extraction Review

Validated on 10 October 2026 against the existing local Docker application at
http://localhost:3003, Oracle metadata storage, routed artifact storage and the
registered Qwen3 model. This is local validation, not an Oracle Kubernetes deployment.

## Findings and corrections

The application's saved conversation trace contained the reported questions.
The uploaded conversation export was not accessible through the file connector;
we used the application's actual saved conversation and tool observations instead.

- A skills question previously read the first six schema fields, omitting skills,
  and the model inferred incorrect matches. Source selection now chooses actual
  fields from the saved result catalog. Typed predicates run against saved values.
  List membership is exact and case-insensitive (Java does not match JavaScript).
- A new count question could inherit a prior React filter. Classification now
  receives the current user request, and count/filter answers are rendered from
  validated tool counts and matches rather than generated guesses. Profile summaries
  also render the semantically selected saved fields directly. A real retest caught
  the model inventing a document-verification claim despite an instruction; direct
  result rendering removes that extra generation step and its unsupported claim.
- Structured-result reads had no numbered citations. They now return record
  references containing extraction ID, saved version, record index and projected
  fields. Clicking a citation opens its extraction in Review. These are references
  to saved values, not a claim of verified PDF coordinates or expertise.
- Review is organized around a dataset filter and searchable extraction ID/file
  directory. It displays ID, dataset, status/version, filename, merged originals
  and stored profile count. The count is calculated from external result JSON;
  result payloads are still excluded from the list API and Oracle metadata tables.
- Merged results support All profiles or one profile, with its original source.
  Save/Cancel are above the fields; long text has multiline controls. Dataset
  changes respect unsaved edits. Desktop fields scroll independently; mobile
  layout stacks the result and source sections.

## Real extraction and browser validation

The fictional QA dataset contains five profiles across two completed merged runs:
Arjun Rao, Meera Iyer and Nikhil Shah in one; Sara Khan and Dev Patel in the other.
This five-profile count applies to the QA dataset, not the user's separate dataset.

Two additional PDFs and a JSON prompt were submitted through Aegis Assistant.
The confirmation step selected merged content with separate records. The actual
upload/index/extraction finished in 97.76 seconds and saved extraction
`982262ef-b010-4afa-8cc4-a1ff8bb35f68`. All stored fields for Sara and Dev matched
known fictional fixture results exactly. Prompt classification, submitted-file
handoff and confirmation were checked through the real browser.

The final browser run passed all four current questions with persisted, versioned
saved-result citations and no browser page errors:

| Question | Observed answer | Seconds |
|---|---|---:|
| Python skill filter | Arjun, Dev and Nikhil only | 36.52 |
| React skill filter | Sara only; skill listing does not prove expertise | 21.73 |
| Profile summary | All five saved profiles, missing phone shown as not provided | 19.00 |
| Count after prior filters | Five profiles across two completed extraction runs | 15.06 |

These are timings from this laptop with Ollama reporting 100% GPU and an 8,192-token
active context, while regression checks were also running. They are not CPU-only
benchmarks or universal performance expectations; earlier warm runs were faster.
Each final answer required one semantic model decision and used actual stored
records for matching, counting and profile summary rendering.

The actual browser also verified clicking a numbered citation, filtering by
selected dataset and exact extraction ID, selecting one profile, rejecting a
dataset change while edits were unsaved, cancelling those edits, and desktop/mobile
layout. The directory displayed two merged originals and two stored profiles.
The original PDF returned HTTP 200, application/pdf and a valid PDF header. The
headless PDF iframe screenshot stayed at the viewer loading surface, so visual
PDF-page rendering is not marked passed. The mobile page provides Open original.
 Earlier raw attempts are not acceptance evidence: the first harness
used a relative HTTP URL without a base URL, and an initial count assertion
incorrectly matched the digit 5 in a citation/filename. Manual inspection caught
that false positive and the subsequent test requires the literal correct count.
Visual inspection also caught an incorrect directory fallback of one profile
when the list response omitted result JSON; the list now supplies profile_count.
A later harness credential-format error was corrected before reaching the app.

## Checks and limits

- 117 backend regression tests passed earlier in this change.
- 32 graph/review tests passed in an earlier focused run. After the final summary
  change, all 26 graph tests passed; the new metadata-only profile-count regression
  also passed separately.
- 99 frontend tests passed using the container dependency image.
- Production container builds, TypeScript validation and static generation passed.
- Browser verification uses real Chromium/Playwright; native computer-use was
  unavailable. Headless PDF rendering is assessed separately from source HTTP
  delivery. No claim is made about live Oracle Kubernetes, cloud deployment,
  equal hardware speeds, or correctness of every possible natural-language query.
