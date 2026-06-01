import { test, expect } from '@playwright/test';

const CREDS = {
  email: 'admin@brightbean.local',
  password: 'admin123',
};

async function login(page) {
  await page.goto('/accounts/login/');

  // AllAuth login form uses #login-form with email + password
  const loginForm = page.locator('form').filter({ has: page.locator('input[name="login"]') });

  // Fill credentials
  await page.fill('input[name="login"]', CREDS.email);
  await page.fill('input[name="password"]', CREDS.password);
  await page.click('button[type="submit"]');

  // Wait for dashboard after login (should redirect to home or dashboard)
  await page.waitForLoadState('networkidle');
}

test.describe('BrightBean Studio — Smoke Tests', () => {

  test('login page loads', async ({ page }) => {
    await page.goto('/accounts/login/');
    await expect(page.locator('input[name="login"]')).toBeVisible({ timeout: 10000 });
  });

  test('can log in with superuser', async ({ page }) => {
    await login(page);

    // After login, we should be redirected to the main app
    // Should NOT be on the login page anymore
    await expect(page).not.toHaveURL(/\/accounts\/login\//);
  });

  test('home page redirects to login when unauthenticated', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/accounts\/login\//);
  });

  test('admin panel is accessible after login', async ({ page }) => {
    await login(page);
    await page.goto('/admin/');
    await expect(page.locator('#site-name')).toBeVisible({ timeout: 10000 });
  });

  test('health check returns 200', async ({ page }) => {
    await page.goto('/health/');
    const body = await page.textContent('body');
    expect(body).toContain('ok');
  });

});
