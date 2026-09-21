// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
import { defineCollection } from 'astro:content';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';
import { heliaFrontmatterSchema } from '@ambiqai/helia-ui/starlight';

export const collections = {
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({ extend: heliaFrontmatterSchema }),
  }),
};
