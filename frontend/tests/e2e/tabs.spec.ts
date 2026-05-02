import { test, expect } from "@playwright/test";

test("tab switching works", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("tab", { name: /by ratings/i })).toHaveAttribute(
    "aria-selected",
    "true"
  );

  await page.getByRole("tab", { name: /by description/i }).click();
  await expect(page.getByRole("tab", { name: /by description/i })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(page.getByPlaceholder(/describe a movie/i)).toBeVisible({
    timeout: 3000,
  });

  await page.getByRole("tab", { name: /by mood/i }).click();
  await expect(page.getByRole("tab", { name: /by mood/i })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(page.getByText(/never stored/i)).toBeVisible({ timeout: 3000 });
});

test("search tab shows example chips", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: /by description/i }).click();
  await expect(page.getByText("dark comedy crime")).toBeVisible({
    timeout: 3000,
  });
});

test("search tab: chip click fills input", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: /by description/i }).click();
  await page.getByText("dark comedy crime").click();
  const input = page.getByPlaceholder(/describe a movie/i);
  await expect(input).toHaveValue("dark comedy crime");
});

test("home page shows hero title", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Find Your Perfect Movie")).toBeVisible();
});
