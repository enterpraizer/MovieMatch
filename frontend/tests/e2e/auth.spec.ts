import { test, expect } from "@playwright/test";

test("register new user and redirect to home", async ({ page }) => {
  const ts = Date.now();
  await page.goto("/register");
  await page.getByPlaceholder("Your name").fill("New User");
  await page.getByPlaceholder("you@example.com").fill(`new_${ts}@test.com`);
  await page.getByPlaceholder("Min 8 chars").fill("NewPass123!");
  await page.getByPlaceholder("Re-enter password").fill("NewPass123!");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL("/", { timeout: 15000 });
});

test("login with wrong password shows error", async ({ page }) => {
  await page.goto("/login");
  await page.getByPlaceholder("you@example.com").fill("nonexistent@test.com");
  await page.getByPlaceholder("Your password").fill("WrongPass1!");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByText(/invalid email or password/i)).toBeVisible({
    timeout: 5000,
  });
});

test("login page has register link", async ({ page }) => {
  await page.goto("/login");
  const link = page.getByRole("link", { name: /register/i });
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("href", "/register");
});
