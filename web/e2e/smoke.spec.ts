/**
 * P3-H browser smoke: the slice renders its states with no backend.
 * No API calls are made here — API behavior is pinned by vitest
 * (client) and pytest (server). Run with `npm run test:e2e` after
 * `npx playwright install chromium`.
 */
import { expect, test } from "@playwright/test";

test("landing shows routes and API status", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Find planets in starlight/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Investigate/ }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /Analyses/ }).first()).toBeVisible();
  await expect(page.getByText("Pipeline status")).toBeVisible();
});

test("investigate renders the honest workspace", async ({ page }) => {
  await page.goto("/investigate");
  await expect(page.getByRole("heading", { name: "Investigate a light curve" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run search" })).toBeVisible();
  await expect(page.getByText("What this page will not show")).toBeVisible();
  await expect(page.getByText(/No “planet probability”/)).toBeVisible();
});

test("simulate is labelled synthetic", async ({ page }) => {
  await page.goto("/simulate");
  await expect(page.getByText("SYNTHETIC").first()).toBeVisible();
});

test("settings scopes BYOK honestly", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByText(/sends these keys/)).toBeVisible();
});
