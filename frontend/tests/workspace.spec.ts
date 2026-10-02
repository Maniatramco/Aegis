import { test, expect } from "@playwright/test";
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
    "Knowledge library",
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
test("creates a knowledge base, uploads a document, previews and indexes it", async ({
  page,
}) => {
  const suffix = Date.now().toString();
  const kb = `Browser QA ${suffix}`;
  const filename = `browser-${suffix}.txt`;
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Knowledge library", exact: true })
    .click();
  await page.getByLabel("New knowledge base name").fill(kb);
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(
    page.getByText("Knowledge base created.", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Upload knowledge base").selectOption({ label: kb });
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
test("mobile navigation remains accessible and sign out removes the session", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
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
