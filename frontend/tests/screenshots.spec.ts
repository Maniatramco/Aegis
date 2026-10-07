import { test, expect, type Page } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { checked, seedMockCatalog, seedDataset, uploadReady } from "./fixtures";

// Run only against the disposable, explicitly mock-enabled Compose deployment.
// Never retain traces/storageState: those can contain authentication material.
test.use({ viewport: { width: 1440, height: 1000 }, locale: "en-US", timezoneId: "UTC", trace: "off", screenshot: "off", video: "off" });
const output = path.resolve("screenshots");
const collection = "Aegis showcase · synthetic project";
const invoiceName = "Northstar-invoice-INV-2026-1042.txt";
const projectName = "Northstar-project-delivery-brief.txt";
const chatSourceName = "Northstar-invoice-summary.txt";
const templateName = "Invoice review · synthetic demo";
const invoice = `SYNTHETIC DEMONSTRATION DOCUMENT — no real customer or payment details.

INVOICE INV-2026-1042
Supplier: Northstar Studio (fictional). Customer: Aegis Demonstration Workspace.
Issue date: 1 October 2026. Currency: USD. Project: Document Intelligence Pilot.
Discovery and information architecture: 20 hours at USD 150 = USD 3,000.
Prototype implementation: 40 hours at USD 150 = USD 6,000.
Accessibility and acceptance testing: 10 hours at USD 150 = USD 1,500.
Subtotal USD 10,500. Tax USD 0. Total due USD 10,500.
Payment terms: net 30 days. Due date: 31 October 2026. No bank details are included.

The pilot deliverables are a searchable knowledge library, answers with inspectable
source citations, and schema-based invoice extraction with a human review step.
Acceptance requires retaining source originals, proving document-scoped retrieval,
and clearly distinguishing development mock output from production model output.

Approval workflow: the project lead checks deliverables, the reviewer compares each
invoice field against the original document, and the workspace administrator verifies
provider configuration. This sample is for interface and integration testing only.`;
const project = `SYNTHETIC PROJECT BRIEF — Document Intelligence Pilot

Objective: make project evidence easier to find without losing the original files.
The first collection contains the Northstar invoice and this delivery brief. Users
should be able to preview both originals, inspect indexed chunks, ask a scoped
question, and review structured fields before exporting JSON or CSV.

Milestone 1, 5 October 2026: upload and index the approved sample documents.
Milestone 2, 12 October 2026: review source-grounded answers and citation previews.
Milestone 3, 19 October 2026: validate extraction templates and export reviewed data.
Acceptance review, 23 October 2026: confirm provenance, access control, and backup steps.

Responsibilities: the fictional project lead owns the delivery checklist; the analyst
reviews citations and extraction results; the administrator owns deployment settings.
Risks include missing source text, stale indexes, and assuming mock output is real AI.
Every development capture must identify mock responses and use synthetic documents.

Success criteria: originals remain downloadable; all completed ingestion jobs have a
ready document; each answer can be checked against a selected source; failed jobs show
an actionable status; provider secrets never appear in screenshots or exported settings.`;

async function navigate(page: Page, name: string) {
  const open = page.getByRole("button", { name: "Open navigation", exact: true });
  if (await open.isVisible() && !await page.locator(".sidebar").evaluate(el => el.classList.contains("open"))) await open.click();
  const nav = page.getByRole("navigation");
  const target = nav.getByRole("button", { name, exact: true });
  if (!await target.isVisible()) await nav.getByRole("button", { name: "Manage workspace", exact: true }).click();
  await target.click();
  await expect(page.getByRole("heading", { name: name === "Dashboard" ? "Workspace overview" : name, exact: true }).first()).toBeVisible();
}
async function capture(page: Page, filename: string) {
  expect(await page.locator(".page-head .btn.primary").evaluateAll(buttons => buttons.every(button => !["transparent", "rgba(0, 0, 0, 0)"].includes(getComputedStyle(button).backgroundColor)))).toBe(true);
  await expect.poll(() => page.locator('img[src="/aegis-logo.png"]').evaluateAll(images => images.length > 0 && images.every(image => (image as HTMLImageElement).complete && (image as HTMLImageElement).naturalWidth > 0))).toBe(true);
  const manage = page.getByRole("button", { name: "Manage workspace", exact: true });
  const primary = await page.locator("main h1").textContent();
  if (["Home", "Datasets", "Ask Aegis", "Extract", "Templates"].includes(primary || "") && await manage.isVisible() && await manage.getAttribute("aria-expanded") === "true") await manage.click();
  // Native Sources dialog makes the background inert, so use the DOM control.
  await expect(page.locator('button[aria-label="Refresh workspace"]')).toBeEnabled();
  const dismiss = page.getByRole("button", { name: "Dismiss notification" });
  if (await dismiss.isVisible()) await dismiss.click();
  await expect(page.getByRole("button", { name: "Dismiss error" })).toHaveCount(0);
  // Assert, rather than hide, any unexpectedly populated credential controls.
  for (const input of await page.locator('input[type="password"]').all()) {
    expect(await input.inputValue()).toBe("");
  }
  await page.evaluate(async () => { await document.fonts.ready; window.scrollTo(0, 0); });
  await page.screenshot({ path: path.join(output, filename), fullPage: true, animations: "disabled" });
}

test("capture all real Aegis screens and dataset model configuration with synthetic sources", async ({ page }) => {
  test.setTimeout(240000);
  const browserErrors: string[] = [];
  page.on("pageerror", error => browserErrors.push(error.message));
  page.on("console", message => { if (message.type() === "error") browserErrors.push(message.text()); });
  const password = process.env.AEGIS_SMOKE_PASSWORD;
  if (!password) throw new Error("AEGIS_SMOKE_PASSWORD is required; run scripts/smoke.py first.");
  await mkdir(output, { recursive: true });
  const session = await checked(await page.request.post("/api/auth/login", {
    data: { username: process.env.AEGIS_SMOKE_USERNAME || "smoke", password },
  }));
  const headers = { "X-CSRF-Token": session.csrf_token };
  const settings = await checked(await page.request.get("/api/settings"));
  expect(settings.model_provider).toBe("mock");
  expect(settings.embedding_provider).toBe("mock");
  const models = await seedMockCatalog(page.request, headers, "Aegis");
  const datasets = await checked(await page.request.get("/api/datasets"));
  const kb = datasets.find((item: { name: string; embedding_model_id: string }) => item.name === collection && item.embedding_model_id === models.embedding.id) ||
    await seedDataset(page.request, headers, collection, [models.fast, models.careful], models.embedding);
  const existing = await checked(await page.request.get(`/api/documents?dataset_id=${kb.id}`));
  const documents = [];
  for (const [name, content] of [[invoiceName, invoice], [projectName, project]]) {
    const document = existing.find((item: { name: string; status: string; requires_reindex: boolean }) => item.name === name && item.status === "ready" && !item.requires_reindex);
    documents.push(document || await uploadReady(page.request, headers, kb, name, content));
  }
  // Concise synthetic evidence lets both real mock-generated turns fit the approved design viewport.
  await uploadReady(page.request, headers, kb, chatSourceName, "SYNTHETIC DEMO. The invoice total is USD 12,480. Payment terms are Net 30 calendar days. Confirm the exact deadline with the issuer.");
  const templates = await checked(await page.request.get("/api/templates"));
  const template = templates.find((item: { name: string }) => item.name === templateName) || await checked(await page.request.post("/api/templates", {
    headers, data: { name: templateName, schema: {
      type: "object", properties: { invoice_number: { type: "string" }, supplier: { type: "string" }, currency: { type: "string" }, total_due: { type: "number" }, due_date: { type: ["string", "null"] } },
      required: ["invoice_number", "supplier", "currency", "total_due", "due_date"], additionalProperties: false,
    } },
  }));

  const inactive = await checked(await page.request.post("/api/datasets", { headers, data: { name: "Archived research · synthetic project", description: "Retained reference documents. Processing is paused.", active: false } }));
  await page.goto("/#Home");
  await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: `Open dataset ${collection}`, exact: true }).getByText("Active", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: `Open dataset ${inactive.name}`, exact: true }).getByText("Inactive", { exact: true })).toBeVisible();
  await capture(page, "00-home.png");
  await page.setViewportSize({ width: 390, height: 844 });
  await capture(page, "00-home-mobile.png");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await navigate(page, "Dashboard");
  await expect(page.getByRole("row").filter({ hasText: invoiceName })).toBeVisible();
  await capture(page, "01-dashboard.png");
  await navigate(page, "Datasets");
  await page.getByRole("button", { name: `Open dataset ${collection}`, exact: true }).first().click();
  await page.getByRole("button", { name: "Documents", exact: true }).click();
  await expect(page.getByRole("row").filter({ hasText: invoiceName }).getByText("ready", { exact: true })).toBeVisible();
  await capture(page, "02-datasets.png");
  await page.getByRole("button", { name: "Map models", exact: true }).click();
  await expect(page.getByLabel(`Mapped model ${models.fast.name}`, { exact: true })).toBeChecked();
  await expect(page.getByLabel(`Mapped model ${models.careful.name}`, { exact: true })).toBeChecked();
  await expect(page.getByLabel("Default chat model", { exact: true })).toHaveValue(models.fast.id);
  await capture(page, "11-dataset-models.png");

  await navigate(page, "Ask Aegis");
  await page.getByLabel("Chat dataset", { exact: true }).selectOption(kb.id);
  await page.getByRole("combobox", { name: "Chat model", exact: true }).selectOption(models.careful.id);
  await page.setViewportSize({ width: 1487, height: 1058 });
  await capture(page, "12-ask-start.png");
  await page.setViewportSize({ width: 390, height: 844 });
  await capture(page, "12-ask-mobile.png");
  await page.setViewportSize({ width: 1487, height: 1058 });
  await page.locator("summary").filter({ hasText: /^Document scope/ }).click();
  await page.getByRole("checkbox", { name: new RegExp(chatSourceName.replaceAll(".", "\\.")) }).check();
  const chatConsent = page.getByRole("checkbox", { name: /I approve sending this request/ });
  if (await chatConsent.isVisible()) await chatConsent.check();
  await page.getByLabel("Ask a question").fill("What are the invoice total and payment terms?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("MOCK TEST OUTPUT", { exact: true })).toBeVisible();
  await expect(page.getByTitle("Copy answer")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop", exact: true })).toHaveCount(0);
  await expect(page.locator(".citation").first()).toBeVisible();
  await page.locator("summary").filter({ hasText: /^Document scope/ }).click();
  await capture(page, "03-ask-aegis.png");
  // Second answer is generated by the actual mock-enabled backend, never a
  // screenshot-only fixture or substituted API response.
  if (await chatConsent.isVisible()) await chatConsent.check();
  await page.getByLabel("Ask a question").fill("Does Net 30 mean 30 business days?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTitle("Copy answer")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeVisible();
  await expect(page.locator(".message.user")).toHaveCount(2);
  await expect(page.locator(".message:not(.user)")).toHaveCount(2);
  await capture(page, "20-ask-focused-two-answers.png");
  await page.getByRole("button", { name: /^Sources(?: \d+)?$/ }).click();
  await expect(page.getByRole("dialog", { name: "Sources", exact: true })).toContainText(chatSourceName);
  await capture(page, "21-ask-focused-sources.png");
  await page.getByRole("button", { name: "Close sources", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  // The last answer and its source/actions must be reachable above the composer.
  for (const viewport of [{ width: 390, height: 844 }, { width: 320, height: 740 }]) {
    await page.setViewportSize(viewport);
    await page.locator(".chat-messages").evaluate(el => { el.scrollTop = el.scrollHeight; });
    await expect.poll(() => page.getByLabel("Ask a question").evaluate(el => el.scrollHeight <= el.clientHeight + 2)).toBe(true);
    const messageBox = (await page.locator(".chat-messages").boundingBox())!;
    const lastAction = page.getByRole("button", { name: "Unhelpful answer", exact: true }).last();
    const actionBox = (await lastAction.boundingBox())!;
    const composerBox = (await page.locator(".chat-compose-area").boundingBox())!;
    expect(actionBox.y).toBeGreaterThanOrEqual(messageBox.y);
    expect(actionBox.y + actionBox.height).toBeLessThanOrEqual(composerBox.y);
    await page.getByLabel("Ask a question").focus();
    await expect(page.getByLabel("Ask a question")).toBeFocused();
    await capture(page, viewport.width === 390 ? "22-ask-mobile-populated.png" : "24-ask-small-phone.png");
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(".citation").last().click();
  await expect(page.getByRole("dialog", { name: "Sources", exact: true })).toContainText(chatSourceName);
  await capture(page, "23-ask-mobile-sources.png");
  await page.getByRole("button", { name: "Close sources", exact: true }).click();
  await page.setViewportSize({ width: 1440, height: 1000 });

  await navigate(page, "Extract");
  await page.getByLabel("Extraction dataset", { exact: true }).selectOption(kb.id);
  await page.getByRole("combobox", { name: "Extraction model", exact: true }).selectOption(models.careful.id);
  await page.getByRole("checkbox", { name: new RegExp(invoiceName.replaceAll(".", "\\.")) }).check();
  await page.getByLabel("Extraction template").selectOption(template.id);
  const extractionConsent = page.getByRole("checkbox", { name: /I approve sending this request/ });
  if (await extractionConsent.isVisible()) await extractionConsent.check();
  await capture(page, "13-extract-start.png");
  await page.setViewportSize({ width: 390, height: 844 });
  await capture(page, "13-extract-mobile.png");
  await page.setViewportSize({ width: 1440, height: 1000 });
  const created = page.waitForResponse(r => r.url().endsWith("/api/extractions") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Run extraction", exact: true }).click();
  const extraction = await checked(await created);
  expect(extraction.model_selection).toMatchObject({ dataset_id: kb.id, model_id: models.careful.id });
  await expect.poll(async () => {
    const result = await checked(await page.request.get(`/api/extractions/${extraction.id}`));
    if (result.status === "failed") throw new Error("Synthetic extraction job failed");
    return result.status;
  }, { timeout: 90000 }).toBe("ready");
  await page.getByTitle("Reload extraction").click();
  await expect(page.getByLabel("Extraction result JSON")).toHaveValue(/MOCK TEST VALUE/);
  await expect(page.getByText(/MOCK TEST OUTPUT · Synthetic development data/)).toBeVisible();
  await page.getByLabel("Refresh workspace").click();
  await expect(page.getByRole("heading", { name: "Review extraction", exact: true })).toBeVisible();
  await capture(page, "04-extract.png");
  await page.getByRole("button", { name: "Extraction history", exact: true }).click();
  await expect(page.getByRole("heading", { name: templateName, exact: true }).first()).toBeVisible();
  await capture(page, "14-extract-history.png");

  await navigate(page, "Templates");
  await expect(page.getByLabel("Template name", { exact: true })).toHaveValue(templateName);
  await capture(page, "05-templates.png");
  await navigate(page, "Index inspector");
  await page.getByLabel("Document to inspect").selectOption(documents[0].id);
  await page.getByRole("button", { name: "Inspect index", exact: true }).click();
  await expect(page.locator("pre.code").filter({ hasText: "INV-2026-1042" }).first()).toBeVisible();
  await capture(page, "06-index-inspector.png");
  await navigate(page, "Jobs & activity");
  await expect(page.getByText("completed", { exact: true }).first()).toBeVisible();
  await capture(page, "07-jobs-activity.png");
  await navigate(page, "Connections");
  await expect(page.getByLabel("Model provider", { exact: true })).not.toBeVisible();
  await capture(page, "08-connections.png");
  for (const [tab, filename] of [["Profiles", "15-connection-profiles.png"], ["Providers", "16-connection-providers.png"], ["Storage", "17-connection-storage.png"], ["OCI", "18-connection-oci.png"], ["Diagnostics", "19-connection-diagnostics.png"]]) {
    await page.getByRole("button", { name: tab, exact: true }).click();
    if (tab === "Providers") await expect(page.getByLabel("Model provider", { exact: true })).toHaveValue("mock");
    await capture(page, filename);
  }
  await navigate(page, "Services & migration");
  await capture(page, "09-services-migration.png");
  await navigate(page, "Setup");
  await capture(page, "10-setup.png");
  await writeFile(path.join(output, "console-errors.json"), JSON.stringify(browserErrors, null, 2));
  expect(browserErrors).toEqual([]);
  await writeFile(path.join(output, "README.txt"), [
    "Aegis: focused Home, Ask and Extract desktop/mobile views, workspace screens, dataset models, and connection tabs.",
    "Captured by Playwright Chromium against the disposable Docker Compose app in GitHub-hosted CI.",
    "Viewport: 1440 x 1000 workspace, 1487 x 1058 focused Ask, 390 x 844 mobile; full-page captures. No raster mockups or substituted API responses.",
    "All invoice/project content is synthetic. Model and embedding providers explicitly use development mock mode.",
    "The dataset has a named mock connection profile, two mapped chat/extraction models, and a separate embedding model.",
    "Ask start and extraction creation show the multiple-model selector; both requests explicitly use the selected Careful review model.",
    "Chat repeats retrieved evidence; extraction produces MOCK TEST VALUE placeholders and zeros, not real AI output.",
    "Both chat and extraction display visible mock-output labels. No production provider credentials were used.",
    "Authentication used the disposable CI administrator. Credentials, tokens, traces, and storageState are not included.",
    `Captured at: ${new Date().toISOString()}`,
  ].join("\n") + "\n");
});
