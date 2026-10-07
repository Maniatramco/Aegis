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
    await expect(page.getByText(/Ask the local installation owner/)).toBeVisible();
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
  await expect(page.getByRole("link", { name: "Back to sign in" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "screenshots/password-recovery-mobile.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: "screenshots/password-recovery-desktop.png", fullPage: true });
});

test("simple login validates fields and supports keyboard password visibility", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", request => { if (request.url().includes("/api/") && request.method() !== "GET") writes.push(request.url()); });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await page.getByLabel("Username", { exact: true }).fill("");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText("Enter your username.", { exact: true })).toBeVisible();
  await expect(page.getByText("Enter your password.", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Username", { exact: true })).toBeFocused();
  await page.getByLabel("Username", { exact: true }).fill("synthetic-user");
  const password = page.getByLabel("Password", { exact: true });
  await password.fill("synthetic-visibility-only");
  await expect(password).toHaveAttribute("type", "password");
  const show = page.getByRole("button", { name: "Show password", exact: true });
  await show.focus();
  await page.keyboard.press("Enter");
  await expect(password).toHaveAttribute("type", "text");
  await expect(page.getByRole("button", { name: "Hide password", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Enter");
  await expect(password).toHaveAttribute("type", "password");
  expect(writes).toEqual([]);
  await password.fill("");
  await page.getByLabel("Username", { exact: true }).fill("");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "screenshots/login-simple-mobile.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: "screenshots/login-simple-desktop.png", fullPage: true });
});

test("login reports rejected synthetic credentials without leaving the form", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill("nonexistent-synthetic-user");
  await page.getByLabel("Password", { exact: true }).fill("wrong-synthetic-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid username or password");
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeEnabled();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "password");
  await expect(page.getByRole("link", { name: "Forgot password?", exact: true })).toBeVisible();
});

test("private recovery form scrubs the capability, validates and confirms success", async ({ page }) => {
  // Browser presentation contract only; real redemption/security is tested with SQLite in pytest.
  const token = "synthetic-capability-only-aaaaaaaaaaaaaaaaaaaa";
  let resets = 0;
  await page.route("http://127.0.0.1:8000/api/auth/recovery/**", async route => {
    const prepare = route.request().url().endsWith("/prepare");
    if (!prepare) resets++;
    await route.fulfill({ json: prepare ? { username: "Dottie", csrf_token: "synthetic-csrf" } : { ok: true } });
  });
  await page.goto(`/recover-password#recovery=${token}`);
  await expect(page.getByLabel("New password", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/recover-password$/);
  await page.getByRole("button", { name: "Reset password", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("12 to 200");
  await page.getByLabel("New password", { exact: true }).fill("synthetic-Dottie-password");
  await page.getByLabel("Confirm new password", { exact: true }).fill("different-synthetic-password");
  await page.getByRole("button", { name: "Reset password", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("do not match");
  expect(resets).toBe(0);
  await page.getByLabel("Confirm new password", { exact: true }).fill("synthetic-Dottie-password");
  await page.getByRole("button", { name: "Show passwords", exact: true }).click();
  await expect(page.getByLabel("New password", { exact: true })).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Hide passwords", exact: true }).click();
  await page.getByLabel("New password", { exact: true }).fill("");
  await page.getByLabel("Confirm new password", { exact: true }).fill("");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "screenshots/private-recovery-mobile.png", fullPage: true });
  await page.getByLabel("New password", { exact: true }).fill("synthetic-Dottie-password");
  await page.getByLabel("Confirm new password", { exact: true }).fill("synthetic-Dottie-password");
  await page.getByRole("button", { name: "Reset password", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Password changed" })).toBeVisible();
  expect(resets).toBe(1);
  await expect(page.locator("input")).toHaveCount(0);
});

test("expired private recovery link gives a recoverable error without a reset form", async ({ page }) => {
  await page.route("http://127.0.0.1:8000/api/auth/recovery/prepare", route => route.fulfill({ status: 403, json: { detail: "This recovery link is invalid or expired. Open a new private link." } }));
  await page.goto("/recover-password#recovery=synthetic-expired-capability-aaaaaaaaaaaaaaaaa");
  await expect(page.getByRole("alert")).toContainText("expired");
  await expect(page.locator("input")).toHaveCount(0);
  await expect(page).toHaveURL(/\/recover-password$/);
  await page.getByRole("link", { name: "Back to sign in" }).click();
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
});
