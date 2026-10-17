// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  use: { baseURL: 'http://127.0.0.1:8761/neuralspotx/', headless: true },
  webServer: { command: 'npm run preview -- --host 127.0.0.1 --port 8761 --ignore-lock', url: 'http://127.0.0.1:8761/neuralspotx/', reuseExistingServer: false },
});
