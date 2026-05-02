import { test as base, expect } from "@playwright/test";

type Fixtures = {
  authenticatedPage: import("@playwright/test").Page;
};

export const test = base.extend<Fixtures>({
  authenticatedPage: async ({ page }, use) => {
    const ts = Date.now();
    await page.goto("/register");
    await page.getByPlaceholder("Your name").fill("E2E User");
    await page.getByPlaceholder("you@example.com").fill(`e2e_${ts}@test.com`);
    await page.getByPlaceholder("Min 8 chars").fill("TestPass123!");
    await page.getByPlaceholder("Re-enter password").fill("TestPass123!");
    await page.getByRole("button", { name: /create account/i }).click();
    await page.waitForURL("/", { timeout: 15000 });
    await use(page);
  },
});

export { expect };
