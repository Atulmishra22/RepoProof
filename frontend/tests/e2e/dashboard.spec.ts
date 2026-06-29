import { test, expect } from "@playwright/test";

test.describe("RepoProof Live E2E User Flow", () => {
  test("Should log in, handle onboarding, and list repositories", async ({ page }) => {
    // 1. Visit login page
    await page.goto("/login");
    await expect(page).toHaveTitle(/RepoProof/i);

    // 2. Fill out the developer login form
    await page.locator("input#email").fill("developer@repoproof.com");
    await page.locator("input#pass").fill("devpass");

    // 3. Click Developer Login and wait for navigation
    await Promise.all([
      page.waitForURL("**/dashboard", { timeout: 15000 }),
      page.locator("button[type='submit']", { hasText: "Developer Login" }).click(),
    ]);

    // 4. Wait for either Connect GitHub Profile onboarding or Discovered Repositories grid to appear
    const linkProfileHeader = page.locator("h2:has-text('Connect GitHub Profile')");
    const repoHeader = page.locator("h2:has-text('Discovered Repositories')");

    await Promise.race([
      linkProfileHeader.waitFor({ state: "visible", timeout: 10000 }),
      repoHeader.waitFor({ state: "visible", timeout: 10000 }),
    ]).catch(() => {});

    if (await linkProfileHeader.isVisible()) {
      // Enter a mock username in the onboarding field
      await page.locator("input#github_username_onboarding").fill("developer_dev");
      // Click 'Link & Ingest Profile'
      await page.locator("button[type='submit']", { hasText: "Link & Ingest Profile" }).click();
    }

    // 5. Verify the dashboard updates to show the repository listing
    await expect(repoHeader).toBeVisible({ timeout: 15000 });

    // 6. Verify the imported mock repositories (e.g. 'pub-repo') are listed in the grid
    const repoCard = page.locator("h3:has-text('pub-repo')");
    await expect(repoCard).toBeVisible();
  });
});
