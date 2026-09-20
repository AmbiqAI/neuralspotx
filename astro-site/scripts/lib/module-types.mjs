// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/**
 * How a module's declared type is ordered and named on the site.
 *
 * The generator groups pages by it and the catalog's island facets by it, so
 * the two would disagree the first time one of them gained a type
 * (AmbiqAI/neuralspotx#259).
 */

/** The wildcard a manifest uses to declare every target of a kind. */
export const WILDCARD = '*';

/* What the reader sees in place of the wildcard. A facet value has to be a
   value: the filter matches strings, and `*` on a chip reads as a typo. */
export const WILDCARD_LABEL = 'any';

export const TYPE_ORDER = [
  'sdk_provider',
  'soc',
  'board',
  'runtime',
  'portable_api',
  'algorithm',
  'tooling',
  'backend_specific',
];

export const TYPE_GROUPS = {
  sdk_provider: 'SDK providers',
  soc: 'SoC support',
  board: 'Board support',
  runtime: 'Runtimes',
  portable_api: 'Portable APIs',
  algorithm: 'Algorithms',
  tooling: 'Tooling',
  backend_specific: 'Backend specific',
};

export const TYPE_LABELS = {
  sdk_provider: 'SDK provider',
  soc: 'SoC',
  board: 'Board',
  runtime: 'Runtime',
  portable_api: 'Portable API',
  algorithm: 'Algorithm',
  tooling: 'Tooling',
  backend_specific: 'Backend specific',
};

export function typeLabel(type) {
  return TYPE_LABELS[type] ?? type ?? 'Unclassified';
}

/** A manifest's declared targets as facet values, wildcard included. */
export function declaredValues(values) {
  return (values ?? []).map((value) => (value === WILDCARD ? WILDCARD_LABEL : value));
}
