import { test, expect, type Page } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { checked, seedMockCatalog, seedDataset, uploadReady, seedTemplate } from "./fixtures";

test.use({ actionTimeout: 15000 });
const output = path.join(process.cwd(), "screenshots", "responsive");
const screens = ["Home", "Datasets", "Ask Aegis", "Extract", "Templates", "Dashboard", "Index inspector", "Jobs & activity", "Connections", "Services & migration", "Setup"];
async function navigate(page: Page, name: string) {
  await expect(page.locator("main h1")).toBeVisible();
  const open = page.getByRole("button", { name: "Open navigation", exact: true });
  if (await open.isVisible() && !await page.locator(".sidebar").evaluate(el => el.classList.contains("open"))) await open.click();
  const nav = page.getByRole("navigation");
  const target = nav.getByRole("button", { name, exact: true });
  if (!await target.isVisible()) await nav.getByRole("button", { name: "Manage workspace", exact: true }).click();
  await target.click();
  await expect(page.locator("main h1")).toHaveText(name === "Dashboard" ? "Workspace overview" : name);
  await expect(page.getByLabel("Refresh workspace", { exact: true })).toBeEnabled();
}
async function geometry(page: Page) {
  return page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    const visible = (el: Element) => !!el.getClientRects().length && getComputedStyle(el).visibility !== "hidden";
    return {
      width, scrollWidth: document.documentElement.scrollWidth,
      overflow: Array.from(document.querySelectorAll("main *, header *")).filter(visible).filter(el => {
        if (!(el instanceof HTMLElement) || el.parentElement?.closest(".table-scroll, .code")) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && (r.right > width + 1 || r.left < -1);
      }).slice(0, 12).map(el => ({ tag: el.tagName, class: el.className, text: el.textContent?.slice(0, 80), width: el.getBoundingClientRect().width })),
    };
  });
}

test("responsive workspace across phone, tablet, desktop and landscape", async ({ page }) => {
  test.setTimeout(300000);
  const password = process.env.AEGIS_SMOKE_PASSWORD;
  if (!password) throw new Error("AEGIS_SMOKE_PASSWORD is required; run the disposable smoke setup first.");
  await mkdir(output, { recursive: true });
  const session = await checked(await page.request.post("/api/auth/login", { data: { username: process.env.AEGIS_SMOKE_USERNAME || "smoke", password } }));
  const headers = { "X-CSRF-Token": session.csrf_token };
  const models = await seedMockCatalog(page.request, headers, "Responsive synthetic");
  const dataset = await seedDataset(page.request, headers, `Responsive review · synthetic documents ${Date.now()}`, [models.fast, models.careful], models.embedding);
  const sourceDocument = await uploadReady(page.request, headers, dataset, "Synthetic-" + "LongDocumentName".repeat(6) + ".txt", "SYNTHETIC responsive testing document. Reference R-2026. Original documents remain stored. Review and verify the result. ".repeat(20));
  const template = await seedTemplate(page.request, headers, "Synthetic-" + "LongTemplateName".repeat(5));
  const report: unknown[] = [];
  for (const [width, height] of [[320, 740], [390, 844], [768, 1024], [1024, 768], [1440, 1000], [844, 390]]) {
    await page.setViewportSize({ width, height });
    await page.goto("/#Home");
    for (const name of screens) {
      await navigate(page, name);
      if (name === "Ask Aegis") {
        await page.getByLabel("Chat dataset", { exact: true }).selectOption(dataset.id);
        await page.getByRole("combobox", { name: "Chat model", exact: true }).selectOption(models.careful.id);
        await expect(page.getByRole("combobox", { name: "Chat model", exact: true })).toHaveValue(models.careful.id);
      }
      if (name === "Extract") {
        await page.getByLabel("Extraction dataset", { exact: true }).selectOption(dataset.id);
        await page.getByRole("combobox", { name: "Extraction model", exact: true }).selectOption(models.careful.id);
        await page.getByLabel("Extraction template", { exact: true }).selectOption(template.id);
      }
      const dimensions = await geometry(page);
      report.push({ screen: name, height, ...dimensions });
      expect.soft(dimensions.scrollWidth, `${name} body at ${width}`).toBeLessThanOrEqual(width + 1);
      expect.soft(dimensions.overflow, `${name} controls at ${width}`).toEqual([]);
      if (["Home", "Ask Aegis", "Extract", "Connections"].includes(name)) {
        await page.evaluate(async () => { await document.fonts.ready; window.scrollTo(0, 0); });
        await page.screenshot({ path: path.join(output, `${width}x${height}-${name.toLowerCase().replaceAll(" ", "-")}.png`), fullPage: true, animations: "disabled" });
      }
      if (name === "Connections") {
        for (const tab of ["Profiles", "Providers", "Storage", "OCI", "Diagnostics"]) {
          await page.getByRole("button", { name: tab, exact: true }).click();
          const dimensions = await geometry(page);
          report.push({ screen: `Connections/${tab}`, height, ...dimensions });
          expect.soft(dimensions.scrollWidth, `Connections/${tab} body at ${width}`).toBeLessThanOrEqual(width + 1);
          expect.soft(dimensions.overflow, `Connections/${tab} controls at ${width}`).toEqual([]);
        }
      }
    }
  }
  await writeFile(path.join(output, "layout-audit.json"), JSON.stringify(report, null, 2));
  await page.setViewportSize({ width: 320, height: 740 });
  await navigate(page, "Datasets");
  const allDatasets = page.getByRole("button", { name: "All datasets", exact: true });
  if (await allDatasets.isVisible()) await allDatasets.click();
  await page.getByRole("button", { name: `Open dataset ${dataset.name}`, exact: true }).click();
  for (const tab of ["Documents", "Map models", "Settings"]) {
    await page.getByRole("button", { name: tab, exact: true }).click();
    const dimensions = await geometry(page);
    expect.soft(dimensions.scrollWidth, `Dataset/${tab}`).toBeLessThanOrEqual(321);
    expect.soft(dimensions.overflow, `Dataset/${tab}`).toEqual([]);
  }
  await page.getByRole("button", { name: "Documents", exact: true }).click();
  await page.getByRole("button", { name: "Add documents", exact: true }).click();
  expect.soft((await geometry(page)).overflow, "Dataset upload controls").toEqual([]);
  await page.getByRole("button", { name: "Cancel upload", exact: true }).click();
  const table = page.getByRole("region", { name: "Scrollable data table" }).filter({ has: page.getByRole("table") }).first();
  await table.focus();
  await expect(table).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => table.evaluate(el => el.scrollWidth <= el.clientWidth || el.scrollLeft > 0)).toBe(true);

  await navigate(page, "Ask Aegis");
  await page.getByLabel("Chat dataset", { exact: true }).selectOption(dataset.id);
  await page.getByRole("combobox", { name: "Chat model", exact: true }).selectOption(models.careful.id);
  await page.getByRole("checkbox", { name: /I approve sending this request/ }).check();
  await page.getByLabel("Ask a question").fill("What is the reference?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTitle("Copy answer")).toBeVisible();
  expect.soft((await geometry(page)).overflow, "Long citation and answer").toEqual([]);
  await page.getByRole("button", { name: "Conversations", exact: true }).click();
  await page.locator(".chat-list button").first().click();
  expect.soft((await geometry(page)).overflow, "Saved conversation").toEqual([]);

  await navigate(page, "Extract");
  await page.getByLabel("Extraction dataset", { exact: true }).selectOption(dataset.id);
  await page.getByRole("combobox", { name: "Extraction model", exact: true }).selectOption(models.careful.id);
  await page.getByLabel("Extraction template", { exact: true }).selectOption(template.id);
  await page.locator(".selection label").filter({ hasText: sourceDocument.name }).getByRole("checkbox").check();
  await page.getByRole("checkbox", { name: /I approve sending this request/ }).check();
  const pending = page.waitForResponse(r => r.url().endsWith("/api/extractions") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Run extraction", exact: true }).click();
  const extraction = await checked(await pending);
  await expect.poll(async () => (await checked(await page.request.get(`/api/extractions/${extraction.id}`))).status, { timeout: 90000 }).toBe("ready");
  await page.getByTitle("Reload extraction").click();
  await expect(page.getByLabel("Extraction result JSON")).toHaveValue(/MOCK TEST VALUE/);
  expect.soft((await geometry(page)).overflow, "Extraction review").toEqual([]);
  await page.screenshot({ path: path.join(output, "320-extraction-review.png"), fullPage: true });
  await page.getByRole("button", { name: "Extraction history", exact: true }).click();
  expect.soft((await geometry(page)).overflow, "Extraction history").toEqual([]);

  // 1440px browser at 200% zoom has a 720 CSS-pixel layout viewport.
  // This checks that reflow equivalence; it is not native browser-chrome zoom automation.
  await page.setViewportSize({ width: 720, height: 500 });
  for (const name of ["Home", "Ask Aegis", "Extract", "Templates", "Connections", "Setup"]) {
    await navigate(page, name);
    expect.soft((await geometry(page)).overflow, `${name} 200% reflow equivalent`).toEqual([]);
  }
  // Independently enlarge rendered text to 200%, including fixed-pixel declarations.
  await page.setViewportSize({ width: 390, height: 844 });
  for (const name of ["Home", "Ask Aegis", "Extract", "Templates", "Connections", "Setup"]) {
    await page.reload();
    await navigate(page, name);
    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll<HTMLElement>("body *")).map(el => ({ el, size: parseFloat(getComputedStyle(el).fontSize) }));
      for (const { el, size } of items) if (Number.isFinite(size)) el.style.fontSize = `${size * 2}px`;
    });
    expect.soft((await geometry(page)).overflow, `${name} 200% text`).toEqual([]);
    expect.soft((await geometry(page)).scrollWidth, `${name} 200% text body`).toBeLessThanOrEqual(391);
    if (name === "Ask Aegis") await page.screenshot({ path: path.join(output, "390-ask-200-percent-text.png"), fullPage: true });
  }
});

test("drawer supports keyboard, dismissal, resize and short landscape", async ({ page }) => {
  const password = process.env.AEGIS_SMOKE_PASSWORD;
  if (!password) throw new Error("AEGIS_SMOKE_PASSWORD is required");
  await checked(await page.request.post("/api/auth/login", { data: { username: process.env.AEGIS_SMOKE_USERNAME || "smoke", password } }));
  await page.setViewportSize({ width: 320, height: 740 });
  await page.goto("/#Home");
  await expect(page.locator("main h1")).toHaveText("Home");
  const trigger = page.locator(".menu-toggle");
  const sidebar = page.locator(".sidebar");
  await trigger.focus();
  await page.keyboard.press("Tab");
  expect(await page.evaluate(() => !document.activeElement?.closest(".sidebar"))).toBe(true);
  for (const viewport of [{ width: 320, height: 740 }, { width: 768, height: 1024 }, { width: 844, height: 390 }]) {
    await page.setViewportSize(viewport);
    await trigger.click();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
    await expect(sidebar).toHaveAttribute("role", "dialog");
    await expect(page.getByRole("button", { name: "Close navigation", exact: true })).toBeFocused();
    await expect(page.locator(".shell")).toHaveAttribute("inert", "");
    await page.keyboard.press("Shift+Tab");
    expect(await page.evaluate(() => !!document.activeElement?.closest(".sidebar"))).toBe(true);
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Close navigation", exact: true })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    await expect(sidebar).toHaveAttribute("inert", "");
    await trigger.click();
    await page.locator(".navigation-backdrop").click({ position: { x: viewport.width - 8, y: 100 } });
    await expect(trigger).toBeFocused();
    await trigger.click();
    await page.getByRole("navigation").getByRole("button", { name: "Manage workspace", exact: true }).click();
    await page.getByRole("navigation").getByRole("button", { name: "Setup", exact: true }).click();
    await expect(page.locator("main h1")).toHaveText("Setup");
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    await trigger.click();
    await page.getByRole("navigation").getByRole("button", { name: "Manage workspace", exact: true }).click();
    await page.keyboard.press("Escape");
  }
  await trigger.click();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await expect(sidebar).not.toHaveAttribute("role", "dialog");
  await expect(page.locator(".shell")).not.toHaveAttribute("inert", "");
  expect(await page.evaluate(() => document.body.style.overflow)).not.toBe("hidden");
  await expect(sidebar).toBeVisible();
});
