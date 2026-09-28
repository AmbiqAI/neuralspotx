// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
import { test, expect } from '@playwright/test';

test('walkthrough selection and reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('./');
  const journey = page.locator('nsx-journey-walkthrough');
  await journey.scrollIntoViewIfNeeded();
  await journey.getByRole('tab', { name: '5 Flash' }).click();
  await expect(journey).toHaveAttribute('data-stage', '4');
  await expect(journey.getByRole('tabpanel', { name: '5 Flash' })).toBeVisible();
  await page.waitForTimeout(2500);
  await expect(journey).toHaveAttribute('data-stage', '4');
});

test('walkthrough loops after the final step', async ({ page }) => {
  await page.goto('./');
  const journey = page.locator('nsx-journey-walkthrough');
  await journey.scrollIntoViewIfNeeded();
  await journey.getByRole('tab', { name: '6 View' }).click();
  await expect(journey).toHaveAttribute('data-stage', '5');
  await expect(journey).toHaveAttribute('data-stage', '0', { timeout: 15000 });
});

test('walkthrough can pause and resume after a hidden page', async ({ page }) => {
  await page.goto('./');
  const journey = page.locator('nsx-journey-walkthrough');
  await journey.scrollIntoViewIfNeeded();
  await journey.getByRole('tab', { name: '6 View' }).click();
  await journey.getByRole('button', { name: 'Pause', exact: true }).click();
  await page.waitForTimeout(3500);
  await expect(journey).toHaveAttribute('data-stage', '5');
  await journey.getByRole('button', { name: 'Resume', exact: true }).click();
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.waitForTimeout(3500);
  await expect(journey).toHaveAttribute('data-stage', '5');
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(journey).toHaveAttribute('data-stage', '0', { timeout: 15000 });
});

test('active tab pauses typing and outline progress; switching preserves pause', async ({ page }) => {
  await page.goto('./');
  const journey = page.locator('nsx-journey-walkthrough');
  await journey.scrollIntoViewIfNeeded();
  await journey.getByRole('tab', { name: '3 Create' }).click();
  await page.waitForTimeout(400);
  await journey.getByRole('tab', { name: '3 Create' }).click();
  const panel = journey.locator('[data-stage-panel][data-active="true"]');
  const content = await panel.textContent();
  const outline = journey.locator('[aria-selected="true"] rect');
  const progress = await outline.getAttribute('style');
  await page.waitForTimeout(1000);
  expect(await panel.textContent()).toBe(content);
  expect(await outline.getAttribute('style')).toBe(progress);
  await journey.getByRole('tab', { name: '6 View' }).click();
  await expect(journey).toHaveAttribute('data-paused', '');
  await journey.getByRole('tab', { name: '6 View' }).click();
  await expect(journey).not.toHaveAttribute('data-paused');
  await expect(journey).toHaveAttribute('data-stage', '0', { timeout: 15000 });
});
