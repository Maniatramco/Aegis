import { test, expect, type Page } from "@playwright/test";
import { checked, seedMockCatalog, seedDataset, seedTemplate, sessionHeaders, uploadReady } from "./fixtures";
const username = process.env.AEGIS_SMOKE_USERNAME || "smoke";
const password = process.env.AEGIS_SMOKE_PASSWORD;
test.beforeEach(async ({ page }) => {
  if (!password)
    throw new Error(
      "Set AEGIS_SMOKE_PASSWORD to the disposable administrator password seeded by scripts/smoke.py.",
    );
  await page.goto("/#Home");
  await expect.poll(() => page.locator('img[src="/aegis-logo.png"]').evaluateAll(images => images.length > 0 && images.every(image => (image as HTMLImageElement).complete && (image as HTMLImageElement).naturalWidth > 0))).toBe(true);
  await page.getByLabel("Username", { exact: true }).fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ask Aegis", exact: true })).toBeVisible();
  await page.goto("/#Home");
  await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
});
test("navigates all workspace screens and preserves an authenticated refresh", async ({
  page,
}) => {
  for (const name of [
    "Datasets",
    "Ask Aegis",
    "Extract",
    "Re-extract",
    "Prompt templates",
    "Index inspector",
    "Jobs & activity",
    "Connections",
    "Services & migration",
    "Setup",
    "Dashboard",
    "Home",
  ]) {
    await navigate(page, name);
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
    page.getByRole("heading", { name: "Home", exact: true }),
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
  await navigate(page, "Datasets");
  await page.locator(".dataset-intro").getByRole("button", { name: "New dataset", exact: true }).click();
  await page.getByLabel("Dataset name", { exact: true }).fill("Cancelled draft dataset");
  await page.getByRole("button", { name: "Cancel dataset onboarding", exact: true }).click();
  await expect(page.getByLabel("Dataset name", { exact: true })).toHaveCount(0);
  await page.locator(".dataset-intro").getByRole("button", { name: "New dataset", exact: true }).click();
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
  await expect(page.getByLabel("Choose documents")).not.toBeVisible();
  await page.getByRole("button", { name: "Add documents", exact: true }).click();
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
  await navigate(page, "Index inspector");
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
  await expect(page.locator("main h1")).toBeVisible();
  const open = page.getByRole("button", { name: "Open navigation", exact: true });
  if (await open.isVisible() && !await page.locator(".sidebar").evaluate(el => el.classList.contains("open"))) await open.click();
  const nav = page.getByRole("navigation");
  const target = nav.getByRole("button", { name, exact: true });
  if (!await target.isVisible()) await nav.getByRole("button", { name: "Manage workspace", exact: true }).click();
  await target.click();
  await expect(page.getByRole("heading", { name: name === "Dashboard" ? "Workspace overview" : name, exact: true }).first()).toBeVisible();
}

async function openDocumentScope(page: Page) {
  const details = page.locator(".chat-scope");
  if (!await details.evaluate(el => el.hasAttribute("open"))) await details.locator("summary").click();
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
  await page.getByRole("button", { name: "All datasets", exact: true }).click();
  await expect(page.getByRole("link", { name: `Open dataset ${unavailable.name}`, exact: true })).toBeVisible();
  await expect(page.getByRole("button", {name:"Open chat",exact:true})).not.toHaveCount(0);
  await navigate(page, "Ask Aegis");

  await page.getByLabel("Chat dataset", { exact: true }).selectOption(multiple.id);
  const chatModel = page.getByRole("combobox", { name: "Chat model", exact: true });
  await expect(chatModel).toHaveValue(models.fast.id);
  expect((await chatModel.locator("option").evaluateAll(options => options.map(option => (option as HTMLOptionElement).value).filter(Boolean))).sort()).toEqual([models.fast.id, models.careful.id].sort());
  await openDocumentScope(page);
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
  await page.getByLabel("Prompt template", { exact: true }).selectOption(template.id);
  await documentCheckbox(page, documentC.name).check();
  await page.getByRole("checkbox", { name: /I approve sending this request/ }).check();
  await expect(page.getByText("No eligible extraction models", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run extraction", exact: true })).toBeDisabled();
  await expect(page.getByRole("combobox", { name: "Extraction model", exact: true })).toHaveCount(0);

  for (const [dataset, document, model, hasChoice] of [
    [multiple, documentA, models.careful, true],
    [single, documentB, models.separate, false],
  ] as const) {
    await page.getByRole("button", { name: "New extraction", exact: true }).click();
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
  await navigate(page, "Prompt templates");
  await page.getByLabel("Prompt template name", { exact: true }).fill(name);
  await page.getByLabel("Extraction instructions", { exact: true }).fill("Copy the invoice reference without guessing.");
  await page.getByRole("button", {name:"Add field",exact:true}).click();
  await page.getByLabel("Field name /new_field",{exact:true}).fill("invoice_number");
  await page.getByLabel("Extraction instructions",{exact:true}).click();
  await page.getByLabel("Field guidance /invoice_number",{exact:true}).fill("Invoice reference");
  await page
    .getByRole("button", { name: "Save prompt template", exact: true })
    .click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  const savedTemplates=await checked(await page.request.get('/api/templates'));
  expect(savedTemplates.find((t:{name:string})=>t.name===name).schema).toMatchObject({type:'object',description:'Copy the invoice reference without guessing.',properties:{invoice_number:{type:'string',description:'Invoice reference'}},required:['invoice_number'],additionalProperties:false});
  await navigate(page, "Connections");
  await page.getByRole("button", { name: "Providers", exact: true }).click();
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
test("prompt form preserves validation and versions, supports groups and nullable lists, and cancels drafts", async ({page}) => {
  const headers=await sessionHeaders(page.request),name=`Friendly form roundtrip ${Date.now()}`;
  const original={type:'object',properties:{total:{type:'number',minimum:0,description:'Final amount'}},required:['total'],additionalProperties:false};
  const template=await checked(await page.request.post('/api/templates',{headers,data:{name,schema:original}}));
  await page.reload();await navigate(page,'Prompt templates');
  await page.getByRole('article').filter({has:page.getByRole('heading',{name,exact:true})}).getByRole('button',{name:'Edit',exact:true}).click();
  await page.getByLabel('Field guidance /total',{exact:true}).fill('Changed draft');
  await page.getByRole('button',{name:'Cancel changes',exact:true}).click();
  await expect(page.getByLabel('Field guidance /total',{exact:true})).toHaveValue('Final amount');
  await page.getByRole('button',{name:'Add field',exact:true}).click();
  await page.getByLabel('Value type /new_field',{exact:true}).selectOption('object');
  await page.getByRole('button',{name:'Add nested field',exact:true}).click();
  await page.getByLabel('Field name /new_field/new_field',{exact:true}).fill('reference');
  await page.getByLabel('Extraction instructions',{exact:true}).click();
  await page.getByLabel('Field guidance /new_field/reference',{exact:true}).fill('Copy the reference');
  await page.getByRole('button',{name:'Add field',exact:true}).click();
  await page.getByLabel('Value type /new_field_2',{exact:true}).selectOption('array');
  await page.getByLabel('List item type /new_field_2',{exact:true}).selectOption('number');
  await page.getByLabel('May be missing /new_field_2',{exact:true}).check();
  await page.getByRole('button',{name:'Save new version',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'All changes saved'})).toBeVisible();
  const versions=await checked(await page.request.get(`/api/templates/${template.id}/versions`));
  expect(versions).toHaveLength(2);expect(versions[0].schema).toEqual(original);
  expect(versions[1].schema.properties.total).toEqual(original.properties.total);
  expect(versions[1].schema.properties.new_field).toEqual({type:'object',description:'',properties:{reference:{type:'string',description:'Copy the reference'}},required:['reference'],additionalProperties:false});
  expect(versions[1].schema.properties.new_field_2).toEqual({type:['array','null'],description:'',items:{type:'number'}});
  await page.getByLabel('Field guidance /total',{exact:true}).fill('Do not save');
  page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('button',{name:'Home',exact:true}).click();
  await expect(page.getByLabel('Field guidance /total',{exact:true})).toHaveValue('Do not save');
  await page.getByRole('button',{name:'Cancel changes',exact:true}).click();
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
  await page.getByRole("link", { name: `Open dataset ${dataset.name}`, exact: true }).first().click();
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
  await navigate(page, "Jobs & activity");
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

test("Home cards use saved activity, open the right dataset, and retain status after reload", async ({ page }) => {
  const headers = await sessionHeaders(page.request);
  const name = `Home activity ${Date.now()}`;
  const active = await checked(await page.request.post("/api/datasets", { headers, data: { name, description: "Registered without models or documents." } }));
  const inactive = await checked(await page.request.post("/api/datasets", { headers, data: { name: `${name} paused`, active: false } }));
  await page.reload();
  const activeCard = page.getByRole("article", { name: `Dataset ${name}`, exact: true });
  const inactiveCard = page.getByRole("article", { name: `Dataset ${name} paused`, exact: true });
  await expect(activeCard.getByText("Active", { exact: true })).toBeVisible();
  await expect(inactiveCard.getByText("Inactive", { exact: true })).toBeVisible();
  // Active is a saved setting, not an inference from an index, document count, or model readiness.
  expect(active.embedding_model_id).toBeNull();
  await activeCard.getByRole("link", {name: `Open dataset ${name}`,exact:true}).click();
  await expect(page.locator(".dataset-detail").getByRole("heading", { name, exact: true })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`#dataset/${active.id}$`));
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Deactivate dataset", exact: true }).click();
  await expect(page.getByRole("button", { name: "Activate dataset", exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.locator(".dataset-detail").getByText("Dataset status: Inactive", { exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
  await expect(activeCard.getByText("Inactive", { exact: true })).toBeVisible();
  await page.goForward();
  await expect(page.locator(".dataset-detail").getByRole("heading", { name, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Activate dataset", exact: true }).click();
  await expect(page.getByRole("button", { name: "Deactivate dataset", exact: true })).toBeVisible();
  expect((await checked(await page.request.get(`/api/datasets/${active.id}`))).active).toBe(true);
  expect((await checked(await page.request.get(`/api/datasets/${inactive.id}`))).active).toBe(false);
  await navigate(page, "Home");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(activeCard).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await inactiveCard.getByRole("link", {name: `Open dataset ${name} paused`,exact:true}).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".dataset-detail").getByRole("heading", { name: `${name} paused`, exact: true })).toBeVisible();
});

test("Home has accessible loading, error/retry, and empty states", async ({ page }) => {
  // UI state tests deliberately intercept only the dataset response, not provider output.
  let release: () => void = () => {};
  const blocked = new Promise<void>(resolve => { release = resolve; });
  let mode = "loading";
  await page.route("**/api/datasets", async route => {
    if (mode === "loading") await blocked;
    if (mode === "error") await route.fulfill({ status: 503, json: { detail: "Temporary dataset service outage" } });
    else await route.fulfill({ json: [] });
  });
  await page.reload();
  await expect(page.getByRole("status").filter({ hasText: "Loading datasets" })).toBeVisible();
  mode = "error";
  release();
  await expect(page.getByRole("alert").filter({ hasText: "Couldn’t load datasets" })).toBeVisible();
  await expect(page.getByRole("link", { name: /^Open dataset/ })).toHaveCount(0);
  mode = "empty";
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.getByRole("heading", { name: "No registered datasets yet", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Get started", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Datasets", exact: true })).toBeVisible();
});


test("Home dataset links still work when an unrelated dashboard service fails", async ({ page }) => {
  const headers = await sessionHeaders(page.request);
  const name = `Home independent load ${Date.now()}`;
  await checked(await page.request.post("/api/datasets", { headers, data: { name } }));
  await page.route("**/api/overview", route => route.fulfill({ status: 503, json: { detail: "Overview unavailable" } }));
  await page.reload();
  await page.getByRole("link", { name: `Open dataset ${name}`, exact: true }).click();
  await expect(page.locator(".dataset-detail").getByRole("heading", { name, exact: true })).toBeVisible();
});

test("focused screens reveal secondary controls only when requested", async ({ page }) => {
  const nav = page.getByRole("navigation");
  const manage = nav.getByRole("button", { name: "Manage workspace", exact: true });
  await expect(manage).toHaveAttribute("aria-expanded", "false");
  await expect(nav.getByRole("button", { name: "Connections", exact: true })).not.toBeVisible();
  await manage.click();
  await expect(nav.getByRole("button", { name: "Connections", exact: true })).toBeVisible();
  await manage.click();
  await expect(manage).toHaveAttribute("aria-expanded", "false");

  await navigate(page, "Datasets");
  const cards = page.getByRole("link", { name: /^Open dataset / });
  await expect(cards.first()).toBeVisible();
  await expect(page.locator(".dataset-detail")).not.toBeVisible();
  await page.getByLabel("Search datasets", { exact: true }).fill("no-dataset-matches-this-qa-query");
  await expect(page.getByRole("heading", { name: "No matching datasets", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Clear search", exact: true }).click();
  await cards.first().click();
  await expect(cards).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Documents", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Choose documents")).not.toBeVisible();
  await expect(page.getByRole("button", { name: /^(Activate|Deactivate) dataset$/ })).not.toBeVisible();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("button", { name: /^(Activate|Deactivate) dataset$/ })).toBeVisible();
  await page.getByRole("button", { name: "All datasets", exact: true }).click();
  await expect(cards.first()).toBeVisible();

  await navigate(page, "Ask Aegis");
  const scope = page.locator(".chat-scope");
  const history = page.getByRole("button", { name: "Conversations", exact: true });
  await expect(scope).not.toHaveAttribute("open", "");
  await page.getByLabel("Ask a question").fill("Draft survives opening and closing optional controls.");
  await scope.locator("summary").click();
  await scope.locator("summary").click();
  if (!await page.locator(".chat-list").isVisible()) await history.click();
  await page.getByRole("button", { name: "Hide conversations", exact: true }).click();
  await history.click();
  await expect(page.getByLabel("Ask a question")).toHaveValue("Draft survives opening and closing optional controls.");

  await navigate(page, "Extract");
  await expect(page.getByRole("heading", { name: "Create an extraction", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Extraction history", exact: true })).not.toBeVisible();
  await page.getByRole("button", { name: "Extraction history", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Create an extraction", exact: true })).not.toBeVisible();
  await expect(page.getByRole("heading", { name: "Extraction history", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "New extraction", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Create an extraction", exact: true })).toBeVisible();

  await navigate(page, "Connections");
  await expect(page.getByRole("button", { name: "Models", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Model provider", { exact: true })).not.toBeVisible();
  for (const [tab, visible] of [["Providers", "Model provider"], ["Storage", "Storage provider"], ["Providers", "Model provider"]]) {
    await page.getByRole("button", { name: tab, exact: true }).click();
    await expect(page.getByLabel(visible, { exact: true })).toBeVisible();
  }
  await page.getByRole("button", { name: "Profiles", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Connection profiles", exact: true })).toBeVisible();
  await expect(page.getByLabel("OpenAI API key", { exact: true })).not.toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

// Focused-thread interaction checks use real synthetic datasets/model routing.
// Only the explicit interruption/failure cases intercept an answer request.
async function focusedChat(page: Page) {
  const prefix = `Focused chat ${Date.now()}`;
  const headers = await sessionHeaders(page.request);
  const models = await seedMockCatalog(page.request, headers, prefix);
  const dataset = await seedDataset(page.request, headers, prefix, [models.fast, models.careful], models.embedding);
  const source = await uploadReady(page.request, headers, dataset, `${prefix}-evidence.txt`,
    "SYNTHETIC QA SOURCE. The project reference is FOCUS-2042. The review owner is the fictional Northstar team. Delivery is 23 October 2026.");
  await page.reload();
  await navigate(page, "Ask Aegis");
  await page.getByLabel("Chat dataset", { exact: true }).selectOption(dataset.id);
  await page.getByRole("combobox", { name: "Chat model", exact: true }).selectOption(models.careful.id);
  await page.getByRole("checkbox", { name: /I approve sending this request/ }).check();
  return { dataset, models, source };
}
const isAnswerRequest = (url: string) => /\/api\/conversations\/[^/]+\/messages\/stream$/.test(url);

async function showHistory(page: Page) {
  const toggle = page.getByRole("button", { name: "Conversations", exact: true });
  if (!await page.locator(".chat-list").isVisible()) await toggle.click();
  await expect(page.locator(".chat-list")).toBeVisible();
}

test("focused composer preserves IME and Shift+Enter, routes Enter once, and opens cited sources", async ({ page }) => {
  const { dataset, models, source } = await focusedChat(page);
  const input = page.getByLabel("Ask a question");
  let requests = 0;
  page.on("request", request => { if (isAnswerRequest(request.url()) && request.method() === "POST") requests++; });
  await input.fill("What is the project reference?");
  await input.dispatchEvent("compositionstart");
  await input.dispatchEvent("keydown", { key: "Enter", code: "Enter", keyCode: 229, isComposing: true, bubbles: true });
  await input.dispatchEvent("compositionend");
  await expect(input).toHaveValue("What is the project reference?");
  expect(requests).toBe(0);
  await input.press("End");
  await input.press("Shift+Enter");
  await input.press("X");
  await expect(input).toHaveValue("What is the project reference?\nX");
  expect(requests).toBe(0);
  await input.fill("What is the project reference?");
  const pending = page.waitForResponse(response => isAnswerRequest(response.url()) && response.request().method() === "POST");
  await input.press("Enter");
  const response = await pending;
  expect(response.ok()).toBe(true);
  expect(response.request().postDataJSON()).toMatchObject({ dataset_id: dataset.id, model_id: models.careful.id, text: "What is the project reference?" });
  await expect(page.getByTitle("Copy answer")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop", exact: true })).toHaveCount(0);
  await expect(page.locator(".citation").first()).toBeVisible();
  expect(requests).toBe(1);
  await expect(page.locator(".message.user")).toHaveCount(1);
  await expect(page.locator(".message:not(.user)")).toHaveCount(1);
  await page.locator(".citation").first().click();
  const sources = page.getByRole("dialog", { name: "Sources", exact: true });
  await expect(sources).toBeVisible();
  await expect(sources).toContainText(source.name);
  await expect(sources).toContainText("FOCUS-2042");
  await page.getByRole("button", { name: "Close sources", exact: true }).click();
  await expect(sources).not.toBeVisible();
});

test("focused chat blocks duplicate submissions, stops pending output, and retries successfully", async ({ page }) => {
  await focusedChat(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let count = 0;
  await page.route("**/api/conversations/*/messages/stream", async route => {
    count++;
    if (count === 1) {
      await gate;
      await route.abort("aborted").catch(() => {});
    } else await route.continue();
  });
  try {
    const input = page.getByLabel("Ask a question");
    await input.fill("Which team owns the review?");
    // Dispatch in the same event turn to catch races before React renders disabled controls.
    await page.locator("form.composer").evaluate(form => {
      for (let i = 0; i < 3; i++) form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    await expect.poll(() => count).toBe(1);
    await expect(page.getByRole("button", { name: "Stop", exact: true })).toBeVisible();
    await expect(page.getByLabel("Chat dataset", { exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "New conversation", exact: true })).toBeDisabled();
    await page.getByRole("button", { name: "Stop", exact: true }).click();
    release();
    await expect(page.locator(".answer-failure")).toContainText("Generation stopped");
    await expect(page.getByRole("button", { name: "Retry question", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "Retry question", exact: true }).click();
    await expect(page.getByTitle("Copy answer")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Stop", exact: true })).toHaveCount(0);
    await expect(page.locator(".citation").first()).toBeVisible();
    await expect(page.locator(".message.user")).toHaveCount(1);
    await expect(page.locator(".message.assistant:not(.incomplete)")).toHaveCount(1);
    await expect(page.locator(".message.incomplete")).toHaveCount(1);
    expect(count).toBe(2);
  } finally { release(); }
});

test("focused chat recovers a failed request and restores conversation model and document scope", async ({ page }) => {
  const { dataset, models, source } = await focusedChat(page);
  await openDocumentScope(page);
  await documentCheckbox(page, source.name).check();
  let fail = true;
  await page.route("**/api/conversations/*/messages/stream", async route => {
    if (fail) { fail = false; await route.fulfill({ status: 503, json: { detail: "Synthetic temporary answer outage" } }); }
    else await route.continue();
  });
  const question = "What is the delivery date?";
  await page.getByLabel("Ask a question").fill(question);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("Synthetic temporary answer outage", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Retry question", exact: true }).click();
  await expect(page.getByTitle("Copy answer")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop", exact: true })).toHaveCount(0);
  await expect(page.locator(".citation").first()).toBeVisible();
  await page.getByRole("button", { name: "New conversation", exact: true }).click();
  await expect(page.locator(".message")).toHaveCount(0);
  await page.getByRole("combobox", { name: "Chat model", exact: true }).selectOption(models.fast.id);
  await openDocumentScope(page);
  await documentCheckbox(page, source.name).uncheck();
  await askAndCheckRouting(page, "Which team is responsible?", dataset.id, models.fast.id);
  await showHistory(page);
  await page.locator(".chat-list").getByRole("button").filter({ has: page.getByText(question, { exact: true }) }).click();
  await expect(page.getByRole("combobox", { name: "Chat model", exact: true })).toHaveValue(models.careful.id);
  await openDocumentScope(page);
  await expect(documentCheckbox(page, source.name)).toBeChecked();
  await expect(page.locator(".message.user")).toHaveCount(1);
  await expect(page.locator(".message.user")).toContainText(question);
  await expect(page.getByRole("checkbox", { name: /I approve sending this request/ })).not.toBeChecked();
});

test("mobile focused composer expands, stays reachable, and honors reduced motion", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const { dataset, models } = await focusedChat(page);
  const input = page.getByLabel("Ask a question");
  const shortHeight = (await input.boundingBox())!.height;
  await input.fill(Array.from({ length: 12 }, (_, i) => `Question detail ${i + 1}`).join("\n"));
  await expect.poll(async () => (await input.boundingBox())!.height).toBeGreaterThan(shortHeight);
  expect((await input.boundingBox())!.height).toBeLessThan(400);
  await askAndCheckRouting(page, "Give the full project evidence.", dataset.id, models.careful.id);
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  const bounds = (await input.boundingBox())!;
  expect(bounds.y).toBeGreaterThanOrEqual(0);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(844);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const motion = await page.locator(".focused-chat").evaluate(root => {
    return [root, ...root.querySelectorAll("*")].filter(el => el.getClientRects().length).filter(el => {
      const style = getComputedStyle(el);
      const seconds = (value: string) => value.split(",").some(part => parseFloat(part) > 0.001);
      return seconds(style.animationDuration) || seconds(style.transitionDuration) || style.scrollBehavior === "smooth";
    }).map(el => ({ tag: el.tagName, class: el.className }));
  });
  expect(motion).toEqual([]);
});

test("completed answers announce accessibly and preserve a follow-up drafted while waiting", async ({ page }) => {
  await focusedChat(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let reached = false;
  await page.route("**/api/conversations/*/messages/stream", async route => {
    reached = true;
    await gate;
    await route.continue();
  });
  try {
    const input = page.getByLabel("Ask a question");
    await input.fill("Who owns the review?");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect.poll(() => reached).toBe(true);
    await input.fill("Keep this follow-up draft while the first answer completes.");
    release();
    await expect(page.getByRole("button", { name: "Stop", exact: true })).toHaveCount(0);
    await expect(page.locator('.sr-only[role="status"]')).toContainText("Aegis answer:");
    await expect(page.locator('.sr-only[role="status"]')).toContainText("Northstar");
    await expect(input).toHaveValue("Keep this follow-up draft while the first answer completes.");
  } finally { release(); }
});

test("latest history selection and New chat win over stale conversation loads", async ({ page }) => {
  const { dataset } = await focusedChat(page);
  const headers = await sessionHeaders(page.request);
  const suffix = Date.now();
  const a = await checked(await page.request.post("/api/conversations", { headers, data: { title: `History A ${suffix}`, dataset_id: dataset.id, document_ids: [] } }));
  const b = await checked(await page.request.post("/api/conversations", { headers, data: { title: `History B ${suffix}`, dataset_id: dataset.id, document_ids: [] } }));
  await page.getByLabel("Refresh workspace", { exact: true }).click();
  await expect(page.getByLabel("Refresh workspace", { exact: true })).toBeEnabled();
  const gates: Array<{ promise: Promise<void>; release: () => void }> = [];
  for (let i = 0; i < 2; i++) {
    let release!: () => void;
    const promise = new Promise<void>(resolve => { release = resolve; });
    gates.push({ promise, release });
  }
  let loads = 0;
  await page.route(`**/api/conversations/${a.id}`, async route => {
    const gate = gates[loads++];
    await gate.promise;
    await route.continue();
  });
  const choose = (title: string) => page.locator(".chat-list").getByRole("button").filter({ has: page.getByText(title, { exact: true }) });
  try {
    await showHistory(page);
    await choose(a.title).click();
    await expect.poll(() => loads).toBe(1);
    await choose(b.title).click();
    await expect(choose(b.title)).toHaveAttribute("aria-current", "true");
    const first = page.waitForResponse(response => response.url().endsWith(`/api/conversations/${a.id}`));
    gates[0].release();
    await first;
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(choose(b.title)).toHaveAttribute("aria-current", "true");
    await choose(a.title).click();
    await expect.poll(() => loads).toBe(2);
    await page.locator(".chat-heading").getByRole("button", { name: "New conversation", exact: true }).click();
    await page.getByLabel("Ask a question").fill("A fresh draft");
    const second = page.waitForResponse(response => response.url().endsWith(`/api/conversations/${a.id}`));
    gates[1].release();
    await second;
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.getByRole("heading", { name: "What would you like to know?", exact: true })).toBeVisible();
    await expect(page.locator('.chat-list button[aria-current="true"]')).toHaveCount(0);
    await expect(page.getByLabel("Ask a question")).toHaveValue("A fresh draft");
  } finally { gates.forEach(gate => gate.release()); }
});

test("compact conversation dialog restores focus on Escape, Close and backdrop", async ({ page }) => {
  page.setDefaultTimeout(15000);
  await page.setViewportSize({ width: 390, height: 844 });
  await focusedChat(page);
  const trigger = page.getByRole("button", { name: "Conversations", exact: true });
  const history = page.getByRole("dialog", { name: "Saved conversations", exact: true });
  await trigger.click();
  await expect(history).toBeVisible();
  await expect(page.getByRole("button", { name: "Close conversations", exact: true })).toBeFocused();
  // Native modality makes background controls unfocusable; role selectors still find them.
  expect(await history.evaluate(el => el.matches(":modal"))).toBe(true);
  await page.locator('button[aria-label="Open navigation"]').evaluate(el => el.focus());
  await expect(page.getByRole("button", { name: "Close conversations", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(history).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await trigger.click();
  await page.getByRole("button", { name: "Close conversations", exact: true }).click();
  await expect(trigger).toBeFocused();
  await trigger.click();
  await page.mouse.click(385, 400);
  await expect(history).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await trigger.click();
  await history.getByRole("button", { name: "New conversation", exact: true }).click();
  await expect(history).not.toBeVisible();
  await expect(page.getByLabel("Ask a question")).toBeFocused();
  await page.setViewportSize({ width: 1440, height: 540 });
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await trigger.click();
  await expect(page.getByRole("heading", { name: "Conversations", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Manage workspace", exact: true }).click();
  const setup = page.getByRole("navigation").getByRole("button", { name: "Setup", exact: true });
  await setup.scrollIntoViewIfNeeded();
  const box = (await setup.boundingBox())!;
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(540);
  await setup.click();
  await expect(page.locator("main h1")).toHaveText("Setup");
});
