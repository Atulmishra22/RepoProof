import { test, expect } from "@playwright/test";

test.describe("RepoProof Live End-to-End User Flow", () => {
  test("Should execute the complete user pipeline: login, onboarding, select repo, trigger analysis, wait for review, edit facts, chat with AI, approve, and verify outputs with inline refiner", async ({ page }) => {
    // Increase timeout for the deep workflow execution
    test.setTimeout(90000);

    // 1. Visit Login page
    await page.goto("/login");
    await expect(page).toHaveTitle(/RepoProof/i);

    // 2. Fill out the developer login form
    await page.locator("input#email").fill("developer@repoproof.com");
    await page.locator("input#pass").fill("devpass");

    // 3. Click Developer Login and wait for dashboard navigation
    await Promise.all([
      page.waitForURL("**/dashboard", { timeout: 30000 }),
      page.locator("button[type='submit']", { hasText: "Developer Login" }).click(),
    ]);

    // 4. Wait for either Connect GitHub Profile onboarding or Discovered Repositories grid
    const linkProfileHeader = page.locator("h2:has-text('Connect GitHub Profile')");
    const repoHeader = page.locator("h2:has-text('Discovered Repositories')");

    await Promise.race([
      linkProfileHeader.waitFor({ state: "visible", timeout: 10000 }),
      repoHeader.waitFor({ state: "visible", timeout: 10000 }),
    ]).catch(() => {});

    if (await linkProfileHeader.isVisible()) {
      // Enter a mock username in the onboarding field for sandbox testing
      await page.locator("input#github_username_onboarding").fill("developer_dev");
      // Click 'Link & Ingest Profile'
      await page.locator("button[type='submit']", { hasText: "Link & Ingest Profile" }).click();
    }

    // 5. Verify the dashboard updates to show the repository listing
    await expect(repoHeader).toBeVisible({ timeout: 20000 });

    // 6. Verify the imported mock repositories (e.g. 'pub-repo') are listed in the grid
    const repoCard = page.locator("div.group", { hasText: "pub-repo" });
    await expect(repoCard).toBeVisible({ timeout: 20000 });

    // 7. Select pub-repo for analysis
    const checkbox = repoCard.locator("input[type='checkbox']");
    const isChecked = await checkbox.isChecked();
    if (!isChecked) {
      await checkbox.click();
    }

    // Click 'Analyze Selected' to start/restart analysis workflow
    const analyzeBtn = page.locator("button", { hasText: "Analyze Selected" });
    await analyzeBtn.click();

    // 8. Wait for the "Review & Refine" button to appear on the repository card and click it
    const reviewBtn = repoCard.locator("button", { hasText: "Review & Refine" });
    await expect(reviewBtn).toBeVisible({ timeout: 60000 });
    await reviewBtn.click();

    // 9. On the Review page, verify elements and interact
    await page.waitForURL("**/dashboard/review/**", { timeout: 20000 });
    await expect(page.locator("h1", { hasText: "Review extracted claims" })).toBeVisible();

    // Verify candidate claims are loaded
    const factCard = page.locator("div.relative.p-5").first();
    await expect(factCard).toBeVisible({ timeout: 20000 });

    // Input some changes to the first claim's statement
    const statementTextarea = factCard.locator("textarea").first();
    const originalText = await statementTextarea.inputValue();
    await statementTextarea.fill(originalText + " (Modified by Playwright E2E Spec)");

    // Test AI Pairing Refiner chat panel
    const chatInput = page.locator("input[placeholder*='Ask AI to edit']");
    await chatInput.fill("Refine the technology claims to highlight express.js backend development.");
    
    // Target the Send message button specifically using the send icon
    const sendChatBtn = page.locator("button:has(svg.lucide-send)");
    await sendChatBtn.click();

    // Wait for the AI's response to appear in the chat history
    const aiMessage = page.locator("div.bg-\\[\\#161a22\\]").nth(1);
    await expect(aiMessage).toBeVisible({ timeout: 25000 });

    // Click 'Add Custom Claim'
    await page.locator("button", { hasText: "Add Custom Claim" }).click();

    // Click 'Approve & Complete Analysis' to resume pipeline execution
    await page.locator("button", { hasText: "Approve & Complete Analysis" }).click();

    // 10. Verify redirection back to Dashboard and wait for completion
    await page.waitForURL("**/dashboard", { timeout: 20000 });

    // Wait for pub-repo card status to show 'complete'
    const completeStatus = repoCard.locator("span", { hasText: "complete" });
    await expect(completeStatus).toBeVisible({ timeout: 60000 });

    // Click 'View Outputs' on the completed card
    const viewOutputsBtn = repoCard.locator("button", { hasText: "View Outputs" });
    await viewOutputsBtn.click();

    // 11. Verify compiled deliverables on the Outputs page
    await page.waitForURL("**/dashboard/outputs/**", { timeout: 20000 });

    // Check tabs
    const resumeTab = page.locator("button", { hasText: "Resume (PDF & LaTeX)" });
    const linkedinTab = page.locator("button", { hasText: "LinkedIn Summary" });
    const readmeTab = page.locator("button", { hasText: "GitHub README" });
    const portfolioTab = page.locator("button", { hasText: "Developer Portfolio" });

    await expect(resumeTab).toBeVisible();
    await expect(linkedinTab).toBeVisible();
    await expect(readmeTab).toBeVisible();
    await expect(portfolioTab).toBeVisible();

    // Verify resume interactive list is loaded and displays a bullet
    // Select the first clickable bullet in the interactive resume view
    const resumeBullet = page.locator("div.cursor-pointer").first();
    await expect(resumeBullet).toBeVisible({ timeout: 20000 });

    // Click on the bullet to trigger the Line Refiner Panel
    await resumeBullet.click();

    // Verify Line Refiner Panel citation elements
    const citationHeader = page.locator("h3", { hasText: "Line Refiner" });
    await expect(citationHeader).toBeVisible();
    await expect(page.locator("span", { hasText: "Source Evidence File" })).toBeVisible();

    // Refine the line with inline AI instruction
    const refineTextarea = page.locator("textarea#refine-input");
    await refineTextarea.fill("Rephrase this bullet point to highlight express server performance metrics.");
    await page.locator("button[type='submit']", { hasText: "Apply Change with AI" }).click();

    // Verify it updates, refines, and closes selection
    await expect(citationHeader).not.toBeVisible({ timeout: 25050 });
  });
});
