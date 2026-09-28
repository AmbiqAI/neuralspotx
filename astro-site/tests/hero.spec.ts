// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
import { test, expect } from '@playwright/test';

for (const width of [1280, 855, 390]) {
  test(`carousel layout and selection at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 950 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('./');
    const carousel = page.locator('nsx-sdk-carousel');
    const initialHeight = (await carousel.boundingBox())!.height;
    for (const label of ['SDK', 'Modules', 'Targets']) {
      await page.getByRole('button', { name: `Show ${label}`, exact: true }).click();
      await expect(carousel.locator('.active')).toHaveCount(1);
      await expect(carousel.locator('[aria-hidden="false"]')).toHaveCount(1);
      expect((await carousel.boundingBox())!.height).toBe(initialHeight);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    if (width < 992) {
      const actions = await page.locator('.helia-hero__actions').boundingBox();
      const visual = await carousel.boundingBox();
      expect(actions!.y).toBeGreaterThanOrEqual(visual!.y + visual!.height);
    }
  });
}

test('selection resets the cycle, then automatic rotation continues', async ({ page }) => {
  await page.goto('./');
  const modules = page.getByRole('button', { name: 'Show Modules', exact: true });
  await modules.click();
  await page.waitForTimeout(1600);
  await modules.click();
  await page.waitForTimeout(2100);
  await expect(modules).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: 'Show Targets', exact: true })).toHaveAttribute('aria-pressed', 'true', { timeout: 2500 });
});

test('reduced motion keeps the selected view static', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('./');
  const sdk = page.getByRole('button', { name: 'Show SDK', exact: true });
  await page.waitForTimeout(3800);
  await expect(sdk).toHaveAttribute('aria-pressed', 'true');
  await sdk.focus();
  await page.keyboard.press('Tab');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Show Modules', exact: true })).toHaveAttribute('aria-pressed', 'true');
});
