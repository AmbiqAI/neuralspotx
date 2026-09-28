// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
import { test, expect } from '@playwright/test';

test('platform selection synchronizes without moving keyboard focus', async ({ page }) => {
  await page.goto('./getting-started/install/');
  const groups = page.locator('nsx-platform-tabs');
  await expect(groups).toHaveCount(3);
  const linux = groups.first().getByRole('tab', { name: 'Linux', exact: true });
  await linux.click();
  for (const group of await groups.all()) {
    await expect(group.getByRole('tab', { name: 'Linux', exact: true })).toHaveAttribute('aria-selected', 'true');
  }
  await expect(linux).toBeFocused();
  await linux.press('ArrowRight');
  for (const group of await groups.all()) {
    await expect(group.getByRole('tab', { name: 'Windows', exact: true })).toHaveAttribute('aria-selected', 'true');
  }
  await expect(groups.first().getByRole('tab', { name: 'Windows', exact: true })).toBeFocused();
});
