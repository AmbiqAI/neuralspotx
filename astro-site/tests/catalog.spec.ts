// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
import { test, expect } from '@playwright/test';

test('catalog search, facets and reset work together', async ({ page }) => {
  await page.goto('./modules/catalog/');
  const browser = page.locator('[data-slot="module-browser"]');
  const search = page.getByRole('searchbox', { name: 'Search modules' });
  await expect(browser.locator('[data-slot="module-row"]')).toHaveCount(50);
  await search.fill('nsx audio');
  await expect(browser.getByRole('link', { name: 'nsx-audio', exact: true })).toBeVisible();
  await search.fill('no-such-module');
  await expect(browser).toContainText('No modules match');
  await browser.getByRole('button', { name: 'Clear filters' }).click();
  await page.getByRole('combobox', { name: 'Module type', exact: true }).click();
  await page.getByRole('option', { name: 'Library / service', exact: true }).click();
  await expect(browser.locator('[data-slot="module-row"]')).toHaveCount(9);
  await browser.getByRole('button', { name: 'Clear filters' }).click();
  await expect(browser.locator('[data-slot="module-row"]')).toHaveCount(50);
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 950 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});
