import { test, expect, type Page } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { checked } from "./fixtures";

const output = path.join(process.cwd(), "screenshots", "responsive");
const screens = ["Home", "Datasets", "Ask Aegis", "Extract", "Templates", "Dashboard", "Index inspector", "Jobs & activity", "Connections", "Services & migration", "Setup"];
async function navigate(page: Page, name: string) {
  const open = page.getByRole("button", { name: "Open navigation", exact: true });
  if (await open.isVisible()) await open.click();
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
        if (el.closest(".table-scroll, .code, .selection, .chat-messages, .mapping-grid, .catalog-list")) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && (r.right > width + 1 || r.left < -1);
      }).slice(0, 12).map(el => ({ tag: el.tagName, class: el.className, text: el.textContent?.slice(0, 80), width: el.getBoundingClientRect().width })),
    };
  });
}

test("audit responsive workspace across phone, tablet, desktop and landscape", async ({ page }) => {
  test.setTimeout(300000);
  const password = process.env.AEGIS_SMOKE_PASSWORD;
  if (!password) throw new Error("AEGIS_SMOKE_PASSWORD is required; run the disposable smoke setup first.");
  await mkdir(output, { recursive: true });
  await checked(await page.request.post("/api/auth/login", { data: { username: process.env.AEGIS_SMOKE_USERNAME || "smoke", password } }));
  const report: unknown[] = [];
  for (const [width, height] of [[320, 740], [390, 844], [768, 1024], [1024, 768], [1440, 1000], [844, 390]]) {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    for (const name of screens) {
      await navigate(page, name);
      report.push({ screen: name, height, ...(await geometry(page)) });
      if (["Home", "Ask Aegis", "Extract", "Connections"].includes(name)) {
        await page.evaluate(async () => { await document.fonts.ready; window.scrollTo(0, 0); });
        await page.screenshot({ path: path.join(output, `${width}x${height}-${name.toLowerCase().replaceAll(" ", "-")}.png`), fullPage: true, animations: "disabled" });
      }
      if (name === "Connections") {
        for (const tab of ["Profiles", "Providers", "Storage", "OCI", "Diagnostics"]) {
          await page.getByRole("button", { name: tab, exact: true }).click();
          report.push({ screen: `Connections/${tab}`, height, ...(await geometry(page)) });
        }
      }
    }
  }
  await writeFile(path.join(output, "layout-audit.json"), JSON.stringify(report, null, 2));
});
