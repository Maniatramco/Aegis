import { test, expect } from "@playwright/test";

const API_ORIGIN = process.env.AEGIS_TEST_API_URL || "http://127.0.0.1:8000";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/local-recovery", route => route.fulfill({ json: { endpoint: `${API_ORIGIN}/api/auth/recovery` } }));
  await page.route(`${API_ORIGIN}/api/auth/recovery/prepare`, route => route.fulfill({ json: {
    username: "Dottie", csrf_token: "synthetic-csrf",
    mode: route.request().postDataJSON()?.token ? "private" : "local",
  } }));
});

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
    await expect(page.locator('input[type="password"]')).toHaveCount(2);
    await expect(page.getByLabel("Username", { exact: true })).toHaveValue("Dottie");
    if (action === "close") await page.getByRole("link", { name: "Close password recovery" }).click();
    else if (action === "back") await page.getByRole("link", { name: "Back to sign in" }).click();
    else if (action === "escape") await page.keyboard.press("Escape");
    else await page.goBack();
    await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Recover your access" })).toHaveCount(0);
  }
  expect(writes.every(url => url.endsWith("/prepare"))).toBe(true);
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

test("empty installations keep two-field login and require explicit first-account setup", async ({ page }) => {
  const writes: string[] = [];
  await page.route("**/api/auth/status", route => route.fulfill({ json: { setup_required: true } }));
  page.on("request", request => { if (request.url().includes("/api/") && request.method() !== "GET") writes.push(request.url()); });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Welcome back", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Set up your first account", exact: true })).toBeVisible();
  await expect(page.locator(".login-card input")).toHaveCount(2);
  await expect(page.getByLabel("Bootstrap token", { exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Welcome back", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Set up your first account", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Create your workspace", exact: true })).toBeVisible();
  await expect(page.getByLabel("Bootstrap token", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Create administrator", exact: true }).click();
  await expect(page.getByText("Enter your setup code.", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Bootstrap token", { exact: true })).toBeFocused();
  await page.getByLabel("Bootstrap token", { exact: true }).fill("synthetic-unsent-code");
  await page.getByRole("button", { name: "Already configured? Sign in", exact: true }).click();
  await expect(page.locator(".login-card input")).toHaveCount(2);
  await page.getByRole("button", { name: "Set up your first account", exact: true }).click();
  await expect(page.getByLabel("Bootstrap token", { exact: true })).toHaveValue("");
  await page.getByRole("button", { name: "Already configured? Sign in", exact: true }).click();
  expect(writes).toEqual([]);
});

test("login reports rejected synthetic credentials without leaving the form", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill("nonexistent-synthetic-user");
  await page.getByLabel("Password", { exact: true }).fill("wrong-synthetic-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText("Invalid username or password");
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeEnabled();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "password");
  await expect(page.getByRole("link", { name: "Forgot password?", exact: true })).toBeVisible();
});

test("private recovery form scrubs the capability, validates and confirms success", async ({ page }) => {
  // Browser presentation contract only; real redemption/security is tested with SQLite in pytest.
  const token = "synthetic-capability-only-aaaaaaaaaaaaaaaaaaaa";
  let resets = 0;
  await page.route(`${API_ORIGIN}/api/auth/recovery/**`, async route => {
    const prepare = route.request().url().endsWith("/prepare");
    if (!prepare) resets++;
    await route.fulfill({ json: prepare ? { username: "Dottie", csrf_token: "synthetic-csrf" } : { ok: true } });
  });
  await page.goto(`/recover-password#recovery=${token}`);
  await expect(page.getByLabel("New password", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/recover-password$/);
  await page.getByRole("button", { name: "Reset password", exact: true }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText("12 to 200");
  await page.getByLabel("New password", { exact: true }).fill("synthetic-Dottie-password");
  await page.getByLabel("Confirm new password", { exact: true }).fill("different-synthetic-password");
  await page.getByRole("button", { name: "Reset password", exact: true }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText("do not match");
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
  await page.route(`${API_ORIGIN}/api/auth/recovery/prepare`, route => route.fulfill({ status: 403, json: { detail: "This recovery link is invalid or expired. Open a new private link." } }));
  await page.goto("/recover-password#recovery=synthetic-expired-capability-aaaaaaaaaaaaaaaaa");
  await expect(page.locator("main").getByRole("alert")).toContainText("expired");
  await expect(page.locator("input")).toHaveCount(0);
  await expect(page).toHaveURL(/\/recover-password$/);
  await page.getByRole("link", { name: "Back to sign in" }).click();
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
});

test("direct reset needs only a username and matching new passwords", async ({ page }) => {
  const submissions: Record<string, unknown>[] = [];
  await page.route(`${API_ORIGIN}/api/auth/recovery/reset`, async route => {
    submissions.push(route.request().postDataJSON());
    await route.fulfill({ json: { ok: true } });
  });
  await page.goto("/recover-password");
  const username = page.getByLabel("Username", { exact: true });
  const password = page.getByLabel("New password", { exact: true });
  const confirmation = page.getByLabel("Confirm new password", { exact: true });
  const submit = page.getByRole("button", { name: "Reset password", exact: true });
  await expect(username).toHaveValue("Dottie");
  await username.fill("");
  await submit.click();
  await expect(page.getByRole("alert")).toHaveText("Enter your username.");
  await expect(username).toBeFocused();
  await username.fill("Dottie");
  await password.fill("short");
  await confirmation.fill("short");
  await submit.click();
  await expect(page.getByRole("alert")).toContainText("12 to 200");
  await password.fill("synthetic-direct-new-password");
  await confirmation.fill("different-password");
  await submit.click();
  await expect(page.getByRole("alert")).toHaveText("Passwords do not match.");
  expect(submissions).toEqual([]);
  await confirmation.fill("synthetic-direct-new-password");
  await submit.click();
  await expect(page.getByRole("heading", { name: "Password changed" })).toBeVisible();
  expect(submissions).toEqual([{ username: "Dottie", password: "synthetic-direct-new-password", confirmation: "synthetic-direct-new-password" }]);
  await expect(page.locator("input")).toHaveCount(0);
  await page.getByRole("link", { name: "Back to sign in" }).click();
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
});

test("direct reset reports a failed transaction and clears password fields", async ({ page }) => {
  await page.route(`${API_ORIGIN}/api/auth/recovery/reset`, route => route.fulfill({ status: 503, json: { detail: "Password could not be changed. Nothing was committed; try again." } }));
  await page.goto("/recover-password");
  await page.getByLabel("New password", { exact: true }).fill("synthetic-new-password");
  await page.getByLabel("Confirm new password", { exact: true }).fill("synthetic-new-password");
  await page.getByRole("button", { name: "Reset password", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Nothing was committed");
  await expect(page.getByLabel("New password", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Confirm new password", { exact: true })).toHaveValue("");
  await expect(page.getByRole("button", { name: "Reset password", exact: true })).toBeEnabled();
});

test("network deployments give a clear unavailable message", async ({ page }) => {
  await page.route("**/api/local-recovery", route => route.fulfill({ status: 403, json: { detail: "Direct password reset is available only in the local desktop app." } }));
  await page.goto("/recover-password");
  await expect(page.getByRole("alert")).toContainText("only in the local desktop app");
  await expect(page.locator("input")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Back to sign in" })).toBeVisible();
});
