import { test, expect, type Page } from "@playwright/test";
import { checked, seedMockCatalog, seedDataset, seedTemplate, sessionHeaders, uploadReady } from "./fixtures";
const username = process.env.AEGIS_SMOKE_USERNAME || "smoke";
const password = process.env.AEGIS_SMOKE_PASSWORD;
test.beforeEach(async ({ page }) => {
  if (!password)
    throw new Error(
      "Set AEGIS_SMOKE_PASSWORD to the disposable administrator password seeded by scripts/smoke.py.",
    );
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Workspace overview", exact: true }),
  ).toBeVisible();
});
test("navigates all ten screens and preserves an authenticated refresh", async ({
  page,
}) => {
  for (const name of [
    "Datasets",
    "Ask Aegis",
    "Extract",
    "Templates",
    "Index inspector",
    "Jobs & activity",
    "Connections",
    "Services & migration",
    "Setup",
    "Dashboard",
  ]) {
    await page
      .getByRole("navigation")
      .getByRole("button", { name, exact: true })
      .click();
    await expect(
      page
        .getByRole("heading", {
          name: name === "Dashboard" ? "Workspace overview" : name,
          exact: true,
        })
        .first(),
    ).toBeVisible();
  }
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Workspace overview", exact: true }),
  ).toBeVisible();
});
test("onboards a dataset, maps models, uploads a document, previews and indexes it", async ({
  page,
}) => {
  const suffix = Date.now().toString();
  const datasetName = `Browser QA ${suffix}`;
  const filename = `browser-${suffix}.txt`;
  const headers = await sessionHeaders(page.request);
  const models = await seedMockCatalog(page.request, headers, datasetName);
  await page.reload();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Datasets", exact: true })
    .click();
  await page.getByRole("button", { name: "Onboard dataset", exact: true }).click();
  await page.getByLabel("Dataset name", { exact: true }).fill("Cancelled draft dataset");
  await page.getByRole("button", { name: "Cancel dataset onboarding", exact: true }).click();
  await expect(page.getByLabel("Dataset name", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Onboard dataset", exact: true }).click();
  await expect(page.getByLabel("Dataset name", { exact: true })).toHaveValue("");
  await page.getByLabel("Dataset name", { exact: true }).fill(datasetName);
  await page.getByLabel("Dataset description", { exact: true }).fill("Synthetic onboarding evidence for browser QA.");
  const created = page.waitForResponse(r => r.url().endsWith("/api/datasets") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Create dataset", exact: true }).click();
  const dataset = await checked(await created);
  await expect(
    page.getByText("Dataset created. Map its models before adding documents.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Models approved for this dataset", exact: true })).toBeVisible();
  await page.getByLabel(`Mapped model ${models.fast.name}`, { exact: true }).check();
  await page.getByLabel(`Mapped model ${models.careful.name}`, { exact: true }).check();
  await page.getByLabel(`Mapped model ${models.embedding.name}`, { exact: true }).check();
  await page.getByLabel("Default chat model", { exact: true }).selectOption(models.fast.id);
  await page.getByLabel("Default extraction model", { exact: true }).selectOption(models.careful.id);
  await page.getByLabel("Embedding model", { exact: true }).selectOption(models.embedding.id);
  // A workspace refresh returns new dataset objects. Unsaved mapping choices
  // and defaults must survive that real refresh, including the onboarding load.
  const refreshed = page.waitForResponse(r => r.url().endsWith("/api/datasets") && r.request().method() === "GET");
  await page.getByLabel("Refresh workspace", { exact: true }).click();
  await checked(await refreshed);
  await expect(page.getByLabel("Refresh workspace", { exact: true })).toBeEnabled();
  for (const model of [models.fast, models.careful, models.embedding]) {
    await expect(page.getByLabel(`Mapped model ${model.name}`, { exact: true })).toBeChecked();
  }
  await expect(page.getByLabel(`Mapped model ${models.separate.name}`, { exact: true })).not.toBeChecked();
  await expect(page.getByLabel("Default chat model", { exact: true })).toHaveValue(models.fast.id);
  await expect(page.getByLabel("Default extraction model", { exact: true })).toHaveValue(models.careful.id);
  await expect(page.getByLabel("Embedding model", { exact: true })).toHaveValue(models.embedding.id);
  const beforeSave = await checked(await page.request.get(`/api/datasets/${dataset.id}/models`));
  expect(beforeSave.mappings).toEqual([]);
  await page.getByRole("button", { name: "Save model mappings", exact: true }).click();
  await expect.poll(async () => {
    const saved = await checked(await page.request.get(`/api/datasets/${dataset.id}/models`));
    return saved.default_extraction_model_id;
  }).toBe(models.careful.id);
  const saved = await checked(await page.request.get(`/api/datasets/${dataset.id}/models`));
  expect(saved).toMatchObject({ default_chat_model_id: models.fast.id, default_extraction_model_id: models.careful.id, embedding_model_id: models.embedding.id });
  expect(saved.mappings.map((mapping: { model_id: string }) => mapping.model_id).sort()).toEqual([models.fast.id, models.careful.id, models.embedding.id].sort());
  await page.getByRole("button", { name: "Documents", exact: true }).click();
  await page
    .getByLabel("Choose documents")
    .setInputFiles({
      name: filename,
      mimeType: "text/plain",
      buffer: Buffer.from(
        "Aegis browser test evidence. Invoice INV-2026-BROWSER has total 275 dollars. This is synthetic integration-test content.",
      ),
    });
  await page.getByRole("button", { name: "Upload 1", exact: true }).click();
  const row = page.getByRole("row").filter({ hasText: filename });
  await expect(row).toBeVisible();
  await expect(row.getByText("ready", { exact: true })).toBeVisible({
    timeout: 90000,
  });
  await row.getByTitle("Preview document").click();
  await expect(page.getByRole("dialog")).toContainText("INV-2026-BROWSER");
  await page.getByRole("button", { name: "Close preview" }).click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Index inspector", exact: true })
    .click();
  await page
    .getByLabel("Document to inspect")
    .selectOption({ label: filename });
  await page
    .getByRole("button", { name: "Inspect index", exact: true })
    .click();
  await expect(
    page.getByText("INV-2026-BROWSER", { exact: false }).first(),
  ).toBeVisible();
});

async function navigate(page: Page, name: string) {
  await page.getByRole("navigation").getByRole("button", { name, exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true }).first()).toBeVisible();
}

function documentCheckbox(page: Page, filename: string) {
  return page.getByRole("checkbox", { name: new RegExp(filename.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) });
}

async function askAndCheckRouting(page: Page, question: string, datasetId: string, modelId: string) {
  const consent = page.getByRole("checkbox", { name: /I approve sending this request/ });
  if (await consent.isVisible()) await consent.check();
  await page.getByLabel("Ask a question").fill(question);
  const pending = page.waitForResponse(r => /\/api\/conversations\/[^/]+\/messages\/stream$/.test(r.url()) && r.request().method() === "POST");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const response = await pending;
  expect(response.ok()).toBeTruthy();
  expect(response.request().postDataJSON()).toMatchObject({ text: question, dataset_id: datasetId, model_id: modelId });
  // Chromium may discard the body of an SSE resource. Verify the completed UI
  // and canonical stored conversation instead of asking CDP to retrieve it.
  const conversationPath = new URL(response.url()).pathname.replace(/\/messages\/stream$/, "");
  let message: Record<string, any> | undefined;
  await expect.poll(async () => {
    const conversation = await checked(await page.request.get(conversationPath));
    const messages: Record<string, any>[] = conversation.messages;
    const requestIndex = messages.findLastIndex(item => item.role === "user" && item.text === question &&
      item.model_selection?.dataset_id === datasetId && item.model_selection?.model_id === modelId);
    message = requestIndex >= 0 ? messages[requestIndex + 1] : undefined;
    return message?.role === "assistant" ? message.status : undefined;
  }, { message: "The selected-model answer must complete and persist", timeout: 30000 }).toBe("completed");
  expect(message!.model_selection).toMatchObject({ dataset_id: datasetId, model_id: modelId });
  expect(message!.mock).toBe(true);
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeVisible();
  await expect(page.getByTitle("Copy answer").last()).toBeVisible();
  await expect(page.locator(".chat-messages .message").last()).toContainText(message!.text);
  await expect(page.getByRole("button", { name: "Dismiss error" })).toHaveCount(0);
  return message!;
}

test("switches zero, one and multiple mapped models and routes chat and extraction to the selection", async ({ page }) => {
  test.setTimeout(300000);
  const prefix = `Routing QA ${Date.now()}`;
  const headers = await sessionHeaders(page.request);
  const models = await seedMockCatalog(page.request, headers, prefix);
  const multiple = await seedDataset(page.request, headers, `${prefix} · multiple models`, [models.fast, models.careful], models.embedding);
  const single = await seedDataset(page.request, headers, `${prefix} · one model`, [models.separate], models.embedding);
  const unavailable = await seedDataset(page.request, headers, `${prefix} · no generation model`, [], models.embedding);
  const documentA = await uploadReady(page.request, headers, multiple, `${prefix}-cobalt.txt`, "Synthetic dataset A evidence: the launch code is COBALT and the reference is INV-COBALT.");
  const documentB = await uploadReady(page.request, headers, single, `${prefix}-magenta.txt`, "Synthetic dataset B evidence: the launch code is MAGENTA and the reference is INV-MAGENTA.");
  const documentC = await uploadReady(page.request, headers, unavailable, `${prefix}-unconfigured.txt`, "Synthetic document ready for future model configuration.");
  const template = await seedTemplate(page.request, headers, `${prefix} · extraction schema`);
  await page.reload();

  await navigate(page, "Ask Aegis");
  await page.getByLabel("Chat dataset", { exact: true }).selectOption(unavailable.id);
  await page.getByLabel("Ask a question").fill("This must not be sent without a mapped model.");
  await page.getByRole("checkbox", { name: /I approve sending this request/ }).check();
  await expect(page.getByText("No eligible chat models", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
  await expect(page.getByRole("combobox", { name: "Chat model", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Configure dataset models", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Datasets", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Models approved for this dataset", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: `Open dataset ${unavailable.name}`, exact: true })).toContainText("Models needed");
  await navigate(page, "Ask Aegis");

  await page.getByLabel("Chat dataset", { exact: true }).selectOption(multiple.id);
  const chatModel = page.getByRole("combobox", { name: "Chat model", exact: true });
  await expect(chatModel).toHaveValue(models.fast.id);
  expect((await chatModel.locator("option").evaluateAll(options => options.map(option => (option as HTMLOptionElement).value).filter(Boolean))).sort()).toEqual([models.fast.id, models.careful.id].sort());
  await documentCheckbox(page, documentA.name).check();
  await expect(documentCheckbox(page, documentB.name)).toHaveCount(0);
  await chatModel.selectOption(models.careful.id);
  const carefulAnswer = await askAndCheckRouting(page, "What is the launch code?", multiple.id, models.careful.id);
  expect(carefulAnswer.text).toContain("COBALT");
  expect(carefulAnswer.text).not.toContain("MAGENTA");
  expect(carefulAnswer.citations.every((citation: { document_id: string }) => citation.document_id === documentA.id)).toBe(true);
  await chatModel.selectOption(models.fast.id);
  await askAndCheckRouting(page, "Repeat the launch evidence.", multiple.id, models.fast.id);

  await page.getByLabel("Chat dataset", { exact: true }).selectOption(single.id);
  await expect(page.getByRole("combobox", { name: "Chat model", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Chat model", { exact: true })).toContainText(models.separate.name);
  await expect(documentCheckbox(page, documentA.name)).toHaveCount(0);
  await expect(documentCheckbox(page, documentB.name)).not.toBeChecked();
  await documentCheckbox(page, documentB.name).check();
  const singleAnswer = await askAndCheckRouting(page, "What is the launch code?", single.id, models.separate.id);
  expect(singleAnswer.text).toContain("MAGENTA");
  expect(singleAnswer.text).not.toContain("COBALT");
  await page.getByLabel("Chat dataset", { exact: true }).selectOption(multiple.id);
  await expect(chatModel).toHaveValue(models.fast.id);
  await expect(documentCheckbox(page, documentA.name)).not.toBeChecked();

  await navigate(page, "Extract");
  await page.getByLabel("Extraction dataset", { exact: true }).selectOption(unavailable.id);
  await page.getByLabel("Extraction template", { exact: true }).selectOption(template.id);
  await documentCheckbox(page, documentC.name).check();
  await page.getByRole("checkbox", { name: /I approve sending this request/ }).check();
  await expect(page.getByText("No eligible extraction models", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run extraction", exact: true })).toBeDisabled();
  await expect(page.getByRole("combobox", { name: "Extraction model", exact: true })).toHaveCount(0);

  for (const [dataset, document, model, hasChoice] of [
    [multiple, documentA, models.careful, true],
    [single, documentB, models.separate, false],
  ] as const) {
    await page.getByLabel("Extraction dataset", { exact: true }).selectOption(dataset.id);
    const extractModel = page.getByRole("combobox", { name: "Extraction model", exact: true });
    if (hasChoice) {
      await expect(extractModel).toHaveValue(models.fast.id);
      await extractModel.selectOption(model.id);
    } else {
      await expect(extractModel).toHaveCount(0);
      await expect(page.getByLabel("Extraction model", { exact: true })).toContainText(model.name);
    }
    await expect(documentCheckbox(page, document.name)).not.toBeChecked();
    await documentCheckbox(page, document.name).check();
    const consent = page.getByRole("checkbox", { name: /I approve sending this request/ });
    if (await consent.isVisible()) await consent.check();
    const pending = page.waitForResponse(r => r.url().endsWith("/api/extractions") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Run extraction", exact: true }).click();
    const response = await pending;
    expect(response.request().postDataJSON()).toMatchObject({ dataset_id: dataset.id, model_id: model.id, document_ids: [document.id] });
    const extraction = await checked(response);
    await expect.poll(async () => {
      const result = await checked(await page.request.get(`/api/extractions/${extraction.id}`));
      expect(result.model_selection).toMatchObject({ dataset_id: dataset.id, model_id: model.id, provider_model: hasChoice ? "mock-careful" : "mock-separate" });
      if (result.status === "failed") throw new Error("Selected-model extraction failed");
      return result.status;
    }, { timeout: 90000 }).toBe("ready");
    await page.getByTitle("Reload extraction").click();
    await expect(page.getByLabel("Extraction result JSON")).toHaveValue(/MOCK TEST VALUE/);
  }
  await expect(page.getByRole("button", { name: "Dismiss error" })).toHaveCount(0);
});
test("saves a strict template and verifies connections without exposing a key", async ({
  page,
}) => {
  const name = `Browser schema ${Date.now()}`;
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Templates", exact: true })
    .click();
  await page.getByLabel("Template name", { exact: true }).fill(name);
  await page
    .getByLabel("Template JSON schema")
    .fill(
      JSON.stringify({
        type: "object",
        properties: { invoice_number: { type: "string" } },
        required: ["invoice_number"],
        additionalProperties: false,
      }),
    );
  await page
    .getByRole("button", { name: "Save template", exact: true })
    .click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Connections", exact: true })
    .click();
  await expect(page.getByLabel("OpenAI API key", { exact: true })).toHaveValue(
    "",
  );
  await page
    .getByRole("button", { name: "Test saved connections", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Connection test result", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('"database": true', { exact: false }),
  ).toBeVisible();
});
test("mobile dataset and model selection fit the screen and sign out removes the session", async ({
  page,
}) => {
  const datasets = await checked(await page.request.get("/api/datasets"));
  const dataset = datasets.find((item: { models: { enabled: boolean; mapping_enabled: boolean; capabilities: string[] }[] }) =>
    item.models?.filter(model => model.enabled !== false && model.mapping_enabled !== false && model.capabilities.includes("chat")).length > 1,
  );
  expect(dataset, "The smoke fixture must include a dataset with multiple mapped models").toBeTruthy();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await navigate(page, "Datasets");
  await page.getByRole("button", { name: `Open dataset ${dataset.name}`, exact: true }).first().click();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("button", { name: "Map models", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Models approved for this dataset", exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await navigate(page, "Ask Aegis");
  await page.getByLabel("Chat dataset", { exact: true }).selectOption(dataset.id);
  const models = dataset.models.filter((model: { enabled: boolean; mapping_enabled: boolean; capabilities: string[] }) => model.enabled !== false && model.mapping_enabled !== false && model.capabilities.includes("chat"));
  await page.getByRole("combobox", { name: "Chat model", exact: true }).selectOption(models[1].id);
  await expect(page.getByRole("combobox", { name: "Chat model", exact: true })).toHaveValue(models[1].id);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Jobs & activity", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Jobs & activity", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
});
