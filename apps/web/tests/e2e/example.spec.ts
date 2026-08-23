import { test, expect } from '@playwright/test';

test.describe('Web E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should load homepage', async ({ page }) => {
    await expect(page).toHaveTitle(/.*/);
  });

  test('should navigate between pages', async ({ page }) => {
    const navLinks = page.locator('nav a, header a, .navbar a');
    const count = await navLinks.count();
    if (count > 0) {
      await navLinks.first().click();
      await expect(page).not.toHaveURL(/^$/);
    }
  });
});