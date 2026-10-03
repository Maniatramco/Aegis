import { test as base, expect, type Locator, type Page, type Request } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { checked, seedDataset, seedMockCatalog, uploadReady, type Entity, type Headers } from "./fixtures";

// Requires the disposable smoke deployment: actual storage/queue/worker with
// explicitly mock providers. Only named error/latency/notice cases intercept.
// Synthetic screenshots intentionally exclude auth-bearing traces and videos.
const test = base.extend<{ workspace: {
  dataset: Entity; other: Entity; models: Awaited<ReturnType<typeof seedMockCatalog>>;
  headers: Headers; maxMb: number;
} }>({
  workspace: async ({ page }, use, info) => {
    const password = process.env.AEGIS_SMOKE_PASSWORD;
    if (!password) throw new Error("AEGIS_SMOKE_PASSWORD is required; run the disposable smoke setup first.");
    const session = await checked(await page.request.post("/api/auth/login", {
      data: { username: process.env.AEGIS_SMOKE_USERNAME || "smoke", password },
    }));
    const headers = { "X-CSRF-Token": session.csrf_token };
    const models = await seedMockCatalog(page.request, headers, "Chat upload · synthetic");
    const prefix = `Chat upload ${info.testId.slice(-8)} ${Date.now()}`;
    const dataset = await seedDataset(page.request, headers, `${prefix} · review`, [models.fast, models.careful], models.embedding);
    const other = await seedDataset(page.request, headers, `${prefix} · separate`, [models.fast, models.careful], models.embedding);
    const settings = await checked(await page.request.get("/api/settings"));
    await use({ dataset, other, models, headers, maxMb: Number(settings.max_upload_mb) });
  },
});
test.use({ viewport: { width: 1440, height: 1000 }, locale: "en-US", timezoneId: "UTC", trace: "off", screenshot: "off", video: "off", actionTimeout: 15000 });
const synthetic = "SYNTHETIC UI TEST. Review reference ATTACH-2026. Source originals remain stored. New documents are available after indexing completes.";
const file = (name: string, content = synthetic) => ({ name, mimeType: "text/plain", buffer: Buffer.from(content) });
const dialog = (page: Page) => page.getByRole("dialog", { name: "Attach documents", exact: true });
const chatConsent = (page: Page) => page.getByRole("checkbox", { name: /I approve sending this request/ });
const row = (page: Page, name: string) => dialog(page).getByRole("listitem").filter({ has: page.getByText(name, { exact: true }) });
const isUpload = (request: Request) => new URL(request.url()).pathname === "/api/documents/upload" && request.method() === "POST";
const isChatWrite = (request: Request) => /^\/api\/conversations(?:\/|$)/.test(new URL(request.url()).pathname) && request.method() === "POST";
async function navigate(page: Page, name: string) {
  const open = page.getByRole("button", { name: "Open navigation", exact: true });
  if (await open.isVisible() && !await page.locator(".sidebar").evaluate(el => el.classList.contains("open"))) await open.click();
  await page.getByRole("navigation").getByRole("button", { name, exact: true }).click();
  await expect(page.locator("main h1")).toHaveText(name);
  await expect(page.getByLabel("Refresh workspace", { exact: true })).toBeEnabled();
}
async function openChat(page: Page, dataset: Entity) {
  await page.goto("/");
  await expect(page.locator("main h1")).toHaveText("Home");
  await expect(page.getByLabel("Refresh workspace", { exact: true })).toBeEnabled();
  await navigate(page, "Ask Aegis");
  await page.getByLabel("Chat dataset", { exact: true }).selectOption(dataset.id);
}
async function openUploads(page: Page) {
  await page.getByRole("button", { name: "Attach documents", exact: true }).click();
  await expect(dialog(page)).toBeVisible();
}
async function choose(page: Page, files: ReturnType<typeof file>[]) {
  const chooser = page.waitForEvent("filechooser");
  await dialog(page).getByLabel("Choose documents", { exact: true }).click();
  await (await chooser).setFiles(files);
}
async function documents(page: Page, dataset: Entity): Promise<Entity[]> {
  return checked(await page.request.get(`/api/documents?dataset_id=${dataset.id}`));
}
async function screenshot(page: Page, name: string) {
  await mkdir(path.resolve("screenshots"), { recursive: true });
  await expect.poll(() => page.locator('img[src="/aegis-logo.png"]').evaluateAll(images => images.length > 0 && images.every(image => (image as HTMLImageElement).complete && (image as HTMLImageElement).naturalWidth > 0))).toBe(true);
  await page.evaluate(async () => { await document.fonts.ready; });
  await page.screenshot({ path: path.resolve("screenshots", `30-chat-upload-${name}.png`), fullPage: true, animations: "disabled" });
}
async function drop(page: Page, target: Locator, files: ReturnType<typeof file>[]) {
  const transfer = await page.evaluateHandle(items => {
    const data = new DataTransfer();
    for (const item of items) data.items.add(new File([item.content], item.name, { type: item.mimeType, lastModified: 1 }));
    return data;
  }, files.map(item => ({ name: item.name, mimeType: item.mimeType, content: item.buffer.toString("utf8") })));
  try {
    await target.dispatchEvent("dragenter", { dataTransfer: transfer });
    await target.dispatchEvent("dragover", { dataTransfer: transfer });
    await target.dispatchEvent("drop", { dataTransfer: transfer });
  } finally { await transfer.dispose(); }
}
async function noHorizontalOverflow(page: Page) {
  const bounds = await dialog(page).evaluate(el => {
    const rect = el.getBoundingClientRect();
    return { left: rect.left, right: rect.right, width: innerWidth, scroll: el.scrollWidth, client: el.clientWidth, bodyScroll: document.documentElement.scrollWidth };
  });
  expect(bounds.left).toBeGreaterThanOrEqual(0);
  expect(bounds.right).toBeLessThanOrEqual(bounds.width + 1);
  expect(bounds.scroll).toBeLessThanOrEqual(bounds.client + 1);
  expect(bounds.bodyScroll).toBeLessThanOrEqual(bounds.width + 1);
}

test("picker uploads to the selected dataset, preserves model, scope and draft, and never sends chat", async ({ page, workspace: w }) => {
  const original = await uploadReady(page.request, w.headers, w.dataset, "Already-selected-source.txt", synthetic);
  await openChat(page, w.dataset);
  await page.getByRole("combobox", { name: "Chat model", exact: true }).selectOption(w.models.careful.id);
  await page.locator(".chat-scope summary").click();
  await page.getByRole("checkbox", { name: /Already-selected-source\.txt/ }).check();
  await page.locator(".chat-scope summary").click();
  await page.getByLabel("Ask a question").fill("Keep this draft while I attach the review brief.");
  await chatConsent(page).check();
  const uploads: Request[] = [], chats: Request[] = [];
  page.on("request", request => { if (isUpload(request)) uploads.push(request); if (isChatWrite(request)) chats.push(request); });
  await openUploads(page);
  await expect(dialog(page)).toContainText(w.dataset.name);
  await choose(page, [file("Synthetic-review-brief.txt")]);
  await expect(row(page, "Synthetic-review-brief.txt")).toContainText("Ready to upload");
  await screenshot(page, "desktop-chooser");
  const accepted = page.waitForResponse(response => isUpload(response.request()));
  await dialog(page).getByRole("button", { name: "Upload 1", exact: true }).click();
  const result = await checked(await accepted);
  expect(result.documents).toHaveLength(1);
  expect(result.documents[0]).toMatchObject({ dataset_id: w.dataset.id, name: "Synthetic-review-brief.txt" });
  await expect(row(page, "Synthetic-review-brief.txt")).toContainText("Ready for questions", { timeout: 90000 });
  expect(uploads).toHaveLength(1);
  expect(uploads[0].postData()).toContain(`name="dataset_id"\r\n\r\n${w.dataset.id}`);
  expect(uploads[0].postData()).toContain('name="allow_external"\r\n\r\nfalse');
  await screenshot(page, "desktop-ready");
  await dialog(page).getByRole("button", { name: "Close uploads", exact: true }).click();
  await expect(page.getByLabel("Chat dataset", { exact: true })).toHaveValue(w.dataset.id);
  await expect(page.getByRole("combobox", { name: "Chat model", exact: true })).toHaveValue(w.models.careful.id);
  await expect(page.getByLabel("Ask a question")).toHaveValue("Keep this draft while I attach the review brief.");
  await expect(chatConsent(page)).toBeChecked();
  await page.locator(".chat-scope summary").click();
  await expect(page.getByRole("checkbox", { name: /Already-selected-source\.txt/ })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: /Synthetic-review-brief\.txt/ })).not.toBeChecked();
  expect(chats).toEqual([]);
  expect((await documents(page, w.dataset)).map(document => document.id).sort()).toEqual([original.id, result.documents[0].id].sort());
  expect(await documents(page, w.other)).toEqual([]);
});

test("dropping into chat and the panel requires explicit upload", async ({ page, workspace: w }) => {
  await openChat(page, w.dataset);
  await page.getByLabel("Ask a question").fill("This drop must not send my question.");
  const uploads: Request[] = [], chats: Request[] = [];
  page.on("request", request => { if (isUpload(request)) uploads.push(request); if (isChatWrite(request)) chats.push(request); });
  await drop(page, page.locator(".chat-main"), [file("Dropped-chat-evidence.txt")]);
  await expect(dialog(page)).toBeVisible();
  await expect(page.locator(".chat-drop-overlay")).toHaveCount(0);
  await drop(page, dialog(page).locator(".shared-dropzone"), [file("Dropped-panel-evidence.txt")]);
  await expect(dialog(page).getByRole("listitem")).toHaveCount(2);
  expect(uploads).toEqual([]);
  await dialog(page).getByRole("button", { name: "Upload 2", exact: true }).click();
  for (const name of ["Dropped-chat-evidence.txt", "Dropped-panel-evidence.txt"]) await expect(row(page, name)).toContainText("Ready for questions", { timeout: 90000 });
  expect(uploads).toHaveLength(2);
  expect((await documents(page, w.dataset)).map(document => document.name).sort()).toEqual(["Dropped-chat-evidence.txt", "Dropped-panel-evidence.txt"]);
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Ask a question")).toHaveValue("This drop must not send my question.");
  await expect(chatConsent(page)).not.toBeChecked();
  expect(chats).toEqual([]);
});

test("external upload consent is independent from chat and resets for a new dataset", async ({ page, workspace: w }) => {
  // Simulate the notice only. The actual deployment stays local/mock and no
  // synthetic document is transmitted to an external provider.
  await page.route("**/api/settings", async route => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...await response.json(), storage_provider: "oci" } });
  });
  await openChat(page, w.dataset);
  await chatConsent(page).check();
  await openUploads(page);
  await choose(page, [file("Separate-upload-consent.txt")]);
  const consent = dialog(page).getByRole("checkbox", { name: /I approve sending original files/ });
  await expect(consent).not.toBeChecked();
  await expect(dialog(page).getByRole("button", { name: "Upload 1", exact: true })).toBeDisabled();
  await page.keyboard.press("Escape");
  await chatConsent(page).uncheck();
  await openUploads(page);
  await consent.check();
  const accepted = page.waitForResponse(response => isUpload(response.request()));
  await dialog(page).getByRole("button", { name: "Upload 1", exact: true }).click();
  const response = await accepted;
  await checked(response);
  expect(response.request().postData()).toContain('name="allow_external"\r\n\r\ntrue');
  await expect(row(page, "Separate-upload-consent.txt")).toContainText("Ready for questions", { timeout: 90000 });
  await page.keyboard.press("Escape");
  await expect(chatConsent(page)).not.toBeChecked();
  await page.getByLabel("Chat dataset", { exact: true }).selectOption(w.other.id);
  await openUploads(page);
  await expect(consent).not.toBeChecked();
  await expect(dialog(page)).not.toContainText("Separate-upload-consent.txt");
});

test("invalid extension, empty files, configured size and twenty-file limit never upload", async ({ page, workspace: w }) => {
  await openChat(page, w.dataset);
  await openUploads(page);
  const uploads: Request[] = [];
  page.on("request", request => { if (isUpload(request)) uploads.push(request); });
  expect(w.maxMb).toBeGreaterThan(0);
  await choose(page, [file("Unsupported.csv"), file("Empty.txt", ""), { name: "Too-large.txt", mimeType: "text/plain", buffer: Buffer.alloc(w.maxMb * 1024 * 1024 + 1, 65) }]);
  await expect(row(page, "Unsupported.csv")).toContainText("Only PDF, DOCX and UTF-8 TXT files are supported.");
  await expect(row(page, "Empty.txt")).toContainText("Empty files cannot be uploaded.");
  await expect(row(page, "Too-large.txt")).toContainText(`Exceeds the ${w.maxMb} MB upload limit.`);
  await expect(dialog(page).getByRole("button", { name: /^Upload\s*$/ })).toBeDisabled();
  for (const name of ["Unsupported.csv", "Empty.txt", "Too-large.txt"]) await dialog(page).getByRole("button", { name: `Remove ${name}`, exact: true }).click();
  await choose(page, Array.from({ length: 21 }, (_, i) => file(`Synthetic-batch-${i + 1}.txt`)));
  await expect(dialog(page).getByRole("alert")).toContainText("Choose at most 20 files at once");
  await expect(dialog(page).getByRole("listitem")).toHaveCount(0);
  await choose(page, Array.from({ length: 20 }, (_, i) => file(`Synthetic-batch-${i + 1}.txt`)));
  await expect(dialog(page).getByRole("listitem")).toHaveCount(20);
  await expect(dialog(page).getByRole("button", { name: "Upload 20", exact: true })).toBeEnabled();
  await choose(page, [file("One-too-many.txt")]);
  await expect(dialog(page).getByRole("alert")).toContainText("Choose at most 20 files at once");
  await expect(dialog(page).getByRole("listitem")).toHaveCount(20);
  expect(uploads).toEqual([]);
  expect(await documents(page, w.dataset)).toEqual([]);
});

test("definite rejection can be retried without duplicate submissions", async ({ page, workspace: w }) => {
  let attempts = 0;
  await page.route("**/api/documents/upload", async route => {
    attempts += 1;
    if (attempts === 1) await route.fulfill({ status: 413, contentType: "application/json", body: JSON.stringify({ detail: "Synthetic definite upload rejection. Try again." }) });
    else await route.continue();
  });
  await openChat(page, w.dataset);
  await openUploads(page);
  await choose(page, [file("Retry-original-once.txt")]);
  await dialog(page).getByRole("button", { name: "Upload 1", exact: true }).click();
  await expect(row(page, "Retry-original-once.txt")).toContainText("Upload failed");
  await expect(row(page, "Retry-original-once.txt")).toContainText("Synthetic definite upload rejection");
  expect(await documents(page, w.dataset)).toEqual([]);
  // Same-turn activation tests the synchronous lock before React can rerender.
  await dialog(page).getByRole("button", { name: "Retry upload 1", exact: true }).evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
  await expect(row(page, "Retry-original-once.txt")).toContainText("Ready for questions", { timeout: 90000 });
  expect(attempts).toBe(2);
  expect(await documents(page, w.dataset)).toHaveLength(1);
});

test("lost response never resubmits an accepted original or the remaining batch", async ({ page, workspace: w }) => {
  let attempts = 0, acceptedId = "";
  await page.route("**/api/documents/upload", async route => {
    attempts += 1;
    // Store an actual original before losing its response, the precise case
    // where blindly retrying multipart POST would create a duplicate.
    const response = await route.fetch();
    acceptedId = (await response.json()).documents[0].id;
    await route.abort("failed");
  });
  await openChat(page, w.dataset);
  await openUploads(page);
  await choose(page, [file("Response-lost-original.txt"), file("Unsubmitted-next-file.txt")]);
  await dialog(page).getByRole("button", { name: "Upload 2", exact: true }).click();
  await expect(row(page, "Response-lost-original.txt").filter({ hasText: "Upload not confirmed" })).toBeVisible();
  await expect(row(page, "Response-lost-original.txt").filter({ hasText: "Upload not confirmed" })).toContainText("The original may already be stored");
  await expect(row(page, "Unsubmitted-next-file.txt")).toContainText("Ready to upload");
  await expect(dialog(page).getByRole("button", { name: /Retry upload/ })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page.getByLabel("Refresh workspace", { exact: true }).click();
  await expect(page.getByLabel("Refresh workspace", { exact: true })).toBeEnabled();
  await navigate(page, "Home");
  await navigate(page, "Ask Aegis");
  await openUploads(page);
  await expect(row(page, "Response-lost-original.txt").filter({ hasText: "Upload not confirmed" })).toBeVisible();
  expect(attempts).toBe(1);
  expect((await documents(page, w.dataset)).map(document => document.id)).toEqual([acceptedId]);
});

test("failed indexing retries the same stored original after a page reload", async ({ page, workspace: w }) => {
  await openChat(page, w.dataset);
  await openUploads(page);
  const bytes = Buffer.from([0xff, 0xfe, 0xfd, 0x41]); // Real invalid UTF-8; accepted by storage, rejected by worker.
  const uploads: Request[] = [];
  page.on("request", request => { if (isUpload(request)) uploads.push(request); });
  await choose(page, [{ name: "Synthetic-invalid-UTF8.txt", mimeType: "text/plain", buffer: bytes }]);
  const accepted = page.waitForResponse(response => isUpload(response.request()));
  await dialog(page).getByRole("button", { name: "Upload 1", exact: true }).click();
  const result = await checked(await accepted);
  const original = result.documents[0];
  await expect.poll(async () => (await checked(await page.request.get(`/api/documents/${original.id}`))).status, { timeout: 90000 }).toBe("failed");
  await page.reload();
  await expect(page.locator("main h1")).toHaveText("Ask Aegis");
  await expect(page.getByLabel("Refresh workspace", { exact: true })).toBeEnabled();
  await page.getByLabel("Chat dataset", { exact: true }).selectOption(w.dataset.id);
  await openUploads(page);
  await expect(row(page, original.name).getByRole("button", { name: "Retry indexing", exact: true })).toBeEnabled();
  const retried = page.waitForResponse(response => new URL(response.url()).pathname === `/api/documents/${original.id}/reindex` && response.request().method() === "POST");
  await row(page, original.name).getByRole("button", { name: "Retry indexing", exact: true }).evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
  const response = await retried;
  const job = await checked(response);
  expect(response.request().postDataJSON()).toEqual({ allow_external: false });
  expect(job.target_id || job.document_id).toBe(original.id);
  expect(job.id).not.toBe(result.jobs[0].id);
  // A retry cannot repair invalid bytes. Verify honest failure and identical
  // retained original, rather than fabricating a successful indexing response.
  await expect.poll(async () => (await checked(await page.request.get(`/api/documents/${original.id}`))).status, { timeout: 90000 }).toBe("failed");
  expect((await documents(page, w.dataset)).map(document => document.id)).toEqual([original.id]);
  const download = await page.request.get(`/api/documents/${original.id}/download`);
  expect(download.ok()).toBeTruthy();
  expect(await download.body()).toEqual(bytes);
  expect(uploads).toHaveLength(1);
  const jobs: Entity[] = await checked(await page.request.get("/api/jobs"));
  expect(jobs.filter(item => item.kind === "index" && (item.target_id || item.document_id) === original.id)).toHaveLength(2);
});

test("close, navigation and dataset change during delayed upload preserve destination and stop the batch", async ({ page, workspace: w }) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let attempts = 0, acceptedId = "";
  await page.route("**/api/documents/upload", async route => {
    attempts += 1;
    const response = await route.fetch();
    acceptedId = (await response.json()).documents[0].id;
    await gate;
    await route.fulfill({ response });
  });
  try {
    await openChat(page, w.dataset);
    await page.getByLabel("Ask a question").fill("Draft preserved during upload.");
    await openUploads(page);
    await choose(page, [file("Original-destination.txt"), file("Remaining-pending.txt")]);
    await dialog(page).getByRole("button", { name: "Upload 2", exact: true }).evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
    await expect(row(page, "Original-destination.txt").filter({ hasText: "Uploading original" })).toBeVisible();
    await expect(dialog(page).getByLabel("Choose documents")).toBeDisabled();
    await page.keyboard.press("Escape");
    await expect(dialog(page)).not.toBeVisible();
    await expect(page.getByLabel("Ask a question")).toHaveValue("Draft preserved during upload.");
    await openUploads(page);
    await expect(row(page, "Original-destination.txt").filter({ hasText: "Uploading original" })).toBeVisible();
    await dialog(page).getByRole("button", { name: "Close uploads", exact: true }).click();
    await navigate(page, "Home");
    await navigate(page, "Ask Aegis");
    await page.getByLabel("Chat dataset", { exact: true }).selectOption(w.other.id);
    await openUploads(page);
    await expect(dialog(page)).toContainText(w.other.name);
    await expect(dialog(page).getByRole("listitem")).toHaveCount(0);
    release();
    await expect(dialog(page).getByRole("alert")).toContainText("Remaining files were not uploaded");
    expect(attempts).toBe(1);
    expect((await documents(page, w.dataset)).map(document => document.id)).toEqual([acceptedId]);
    expect(await documents(page, w.other)).toEqual([]);
    await page.keyboard.press("Escape");
    await page.getByLabel("Chat dataset", { exact: true }).selectOption(w.dataset.id);
    await openUploads(page);
    await expect(row(page, "Remaining-pending.txt")).toContainText("Ready to upload");
    await expect(row(page, "Original-destination.txt")).toContainText("Ready for questions", { timeout: 90000 });
  } finally { release(); }
});

test("mobile dialog fits narrow and landscape screens with keyboard focus and dismissal", async ({ page, workspace: w }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openChat(page, w.dataset);
  const trigger = page.getByRole("button", { name: "Attach documents", exact: true });
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(dialog(page)).toBeVisible();
  await expect(dialog(page).getByRole("button", { name: "Close uploads", exact: true })).toBeFocused();
  await choose(page, [file("Synthetic-" + "LongDocumentName".repeat(7) + ".txt")]);
  await noHorizontalOverflow(page);
  await screenshot(page, "mobile-chooser");
  const upload = dialog(page).getByRole("button", { name: "Upload 1", exact: true });
  await upload.focus();
  await page.keyboard.press("Tab");
  await expect.poll(() => dialog(page).evaluate(el => el.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog(page)).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await trigger.click();
  await expect(dialog(page).getByRole("listitem")).toHaveCount(1);
  await upload.click();
  await expect(dialog(page).getByText("Ready for questions", { exact: true })).toBeVisible({ timeout: 90000 });
  await screenshot(page, "mobile-ready");
  for (const viewport of [{ width: 320, height: 740 }, { width: 844, height: 390 }]) {
    await page.setViewportSize(viewport);
    await noHorizontalOverflow(page);
    await dialog(page).getByRole("button", { name: "Close uploads", exact: true }).click();
    await expect(dialog(page)).not.toBeVisible();
    await expect(trigger).toBeFocused();
    await trigger.click();
  }
  await page.keyboard.press("Escape");
  expect(await documents(page, w.dataset)).toHaveLength(1);
});

test("missing, inactive and unmapped datasets block attachments until a configured one is selected", async ({ page, workspace: w }) => {
  const unmapped: Entity = await checked(await page.request.post("/api/datasets", {
    headers: w.headers, data: { name: `Unmapped upload · synthetic ${Date.now()}`, description: "Synthetic blocked-upload scenario." },
  }));
  await checked(await page.request.patch(`/api/datasets/${w.other.id}/status`, { headers: w.headers, data: { active: false } }));
  await openChat(page, unmapped);
  await page.getByLabel("Chat dataset", { exact: true }).selectOption("");
  await openUploads(page);
  await expect(dialog(page)).toContainText("Choose a dataset below before attaching documents.");
  await expect(dialog(page).getByLabel("Choose documents", { exact: true })).toBeDisabled();
  await page.keyboard.press("Escape");
  await page.getByLabel("Chat dataset", { exact: true }).selectOption(w.other.id);
  await openUploads(page);
  await expect(dialog(page)).toContainText("This dataset needs an active, mapped embedding model");
  await expect(dialog(page).getByLabel("Choose documents", { exact: true })).toBeDisabled();
  await page.keyboard.press("Escape");
  await page.getByLabel("Chat dataset", { exact: true }).selectOption(unmapped.id);
  await openUploads(page);
  await expect(dialog(page)).toContainText("This dataset needs an active, mapped embedding model");
  await expect(dialog(page).getByLabel("Choose documents", { exact: true })).toBeDisabled();
  await expect(dialog(page).getByRole("button", { name: /^Upload\s*$/ })).toBeDisabled();
  await drop(page, dialog(page).locator(".shared-dropzone"), [file("Must-not-upload.txt")]);
  await expect(dialog(page).getByRole("listitem")).toHaveCount(0);
  expect(await documents(page, unmapped)).toEqual([]);
  await page.keyboard.press("Escape");
  await page.getByLabel("Chat dataset", { exact: true }).selectOption(w.dataset.id);
  await openUploads(page);
  await expect(dialog(page).getByLabel("Choose documents", { exact: true })).toBeEnabled();
  await choose(page, [file("Configured-dataset.txt")]);
  await expect(dialog(page).getByRole("button", { name: "Upload 1", exact: true })).toBeEnabled();
});

test("an explicitly sent question retrieves and cites the original uploaded from chat", async ({ page, workspace: w }) => {
  test.setTimeout(180000);
  await openChat(page, w.dataset);
  await page.getByRole("combobox", { name: "Chat model", exact: true }).selectOption(w.models.careful.id);
  const question = "What is the review reference in the newly uploaded evidence?";
  const filename = "New-chat-answer-evidence.txt";
  await page.getByLabel("Ask a question").fill(question);
  const chats: Request[] = [];
  page.on("request", request => { if (isChatWrite(request)) chats.push(request); });
  await openUploads(page);
  await choose(page, [file(filename, "SYNTHETIC UPLOAD-TO-ANSWER EVIDENCE. The review reference is FRESH-ORIGINAL-2026. This document is newly uploaded from Ask Aegis and retained as the original source.")]);
  const accepted = page.waitForResponse(response => isUpload(response.request()));
  await dialog(page).getByRole("button", { name: "Upload 1", exact: true }).click();
  const uploaded = await checked(await accepted);
  const original = uploaded.documents[0];
  expect(original.dataset_id).toBe(w.dataset.id);
  await expect(row(page, filename)).toContainText("Ready for questions", { timeout: 90000 });
  await dialog(page).getByRole("button", { name: "Close uploads", exact: true }).click();
  await expect(page.getByLabel("Ask a question")).toHaveValue(question);
  await expect(chatConsent(page)).not.toBeChecked();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
  expect(chats).toEqual([]);

  await page.locator(".chat-scope summary").click();
  const source = page.getByRole("checkbox", { name: /New-chat-answer-evidence\.txt/ });
  await expect(source).not.toBeChecked();
  await source.check();
  await page.locator(".chat-scope summary").click();
  await chatConsent(page).check();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeEnabled();
  // Upload, indexing, scope changes and consent are all preparatory. Only this
  // deliberate Send action may create a conversation or request an answer.
  expect(chats).toEqual([]);
  const answered = page.waitForResponse(response => /\/api\/conversations\/[^/]+\/messages\/stream$/.test(new URL(response.url()).pathname) && response.request().method() === "POST");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const response = await answered;
  expect(response.ok()).toBeTruthy();
  expect(response.request().postDataJSON()).toEqual({
    text: question, dataset_id: w.dataset.id, model_id: w.models.careful.id,
    document_ids: [original.id], allow_external: true,
  });
  const conversationPath = new URL(response.url()).pathname.replace(/\/messages\/stream$/, "");
  let answer: Entity | undefined;
  await expect.poll(async () => {
    const conversation = await checked(await page.request.get(conversationPath));
    const messages: Entity[] = conversation.messages;
    const requestIndex = messages.findLastIndex(message => message.role === "user" && message.text === question);
    answer = requestIndex >= 0 ? messages[requestIndex + 1] : undefined;
    return answer?.role === "assistant" ? answer.status : undefined;
  }, { timeout: 30000, message: "The answer and citations must persist in the real conversation" }).toBe("completed");
  expect(answer!.mock).toBe(true);
  expect(answer!.model_selection).toMatchObject({ dataset_id: w.dataset.id, model_id: w.models.careful.id });
  expect(answer!.text).toContain("FRESH-ORIGINAL-2026");
  expect(answer!.citations.length).toBeGreaterThan(0);
  expect(answer!.citations.every((citation: Entity) => citation.document_id === original.id && citation.document_name === filename)).toBe(true);
  await expect(page.getByTitle("Copy answer").last()).toBeVisible();
  await expect(page.locator(".chat-messages .message").last()).toContainText("FRESH-ORIGINAL-2026");
  await expect(page.locator(".answer-citations")).toContainText(filename);
  const creation = chats.find(request => new URL(request.url()).pathname === "/api/conversations");
  expect(creation?.postDataJSON()).toMatchObject({ dataset_id: w.dataset.id, document_ids: [original.id] });
  expect(chats.filter(request => /\/messages\/stream$/.test(request.url()))).toHaveLength(1);
  expect((await documents(page, w.dataset)).map(document => document.id)).toEqual([original.id]);
  await expect(page.getByRole("button", { name: "Dismiss error" })).toHaveCount(0);
});
