import { test, expect } from "@playwright/test";

test("login recovery supports close, back, Escape and repeated navigation without writes", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", request => {
    if (request.url().includes("/api/") && request.method() !== "GET") writes.push(request.url());
  });
  await page.goto("/");
  // A clean installation may initially show first-run setup.
  const existing = page.getByRole("button", { name: "Already configured? Sign in", exact: true });
  if (await existing.isVisible()) await existing.click();
  const forgot = page.getByRole("link", { name: "Forgot password?", exact: true });
  await expect(forgot).toBeVisible();
  for (const action of ["close", "back", "escape", "browser-back"]) {
    await forgot.click();
    const heading = page.getByRole("heading", { name: "Recover your access", exact: true });
    await expect(heading).toBeVisible();
    await expect(heading).toBeFocused();
    await expect(page.locator('input[type="password"]')).toHaveCount(0);
    await page.getByText("Local operator instructions", { exact: true }).click();
    await expect(page.locator("pre")).toContainText("reset_admin_password.py");
    await expect(page.locator("pre")).not.toContainText("--password");
    if (action === "close") await page.getByRole("link", { name: "Close password recovery" }).click();
    else if (action === "back") await page.getByRole("link", { name: "Back to sign in" }).click();
    else if (action === "escape") await page.keyboard.press("Escape");
    else await page.goBack();
    await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Recover your access" })).toHaveCount(0);
  }
  expect(writes).toEqual([]);
});

test("recovery deep link works on mobile and reloads without overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/recover-password");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Recover your access" })).toBeVisible();
  await page.getByText("Local operator instructions", { exact: true }).click();
  await expect(page.getByRole("link", { name: "Back to sign in" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "screenshots/password-recovery-mobile.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: "screenshots/password-recovery-desktop.png", fullPage: true });
});
