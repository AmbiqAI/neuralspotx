// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
import * as React from 'react';
import { Button } from '@ambiqai/helia-ui/react/button';
import { Input } from '@ambiqai/helia-ui/react/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@ambiqai/helia-ui/react/select';
export interface CatalogModule {
  name: string;
  href: string;
  type: string;
  summary: string;
  version: string;
  socs: string[];
  boards: string[];
  toolchains: string[];
  capabilities: string[];
  depends: { required: string[]; optional: string[] };
}

export interface ModuleBrowserProps {
  modules: CatalogModule[];
  /** The value a manifest uses to declare every target of a kind. */
  wildcard?: string;
}

/* Radix rejects an empty option value, so the unfiltered state needs a value
   of its own rather than the empty string. */
const ANY = '__any__';

type FacetId = 'type' | 'soc' | 'board' | 'toolchain' | 'capability';

const FACETS: { id: FacetId; label: string; of: (module: CatalogModule) => string[] }[] = [
  { id: 'capability', label: 'Capability', of: (module) => module.capabilities },
  { id: 'type', label: 'Module type', of: (module) => [module.type] },
  { id: 'soc', label: 'SoC', of: (module) => module.socs },
  { id: 'board', label: 'Board', of: (module) => module.boards },
  { id: 'toolchain', label: 'Toolchain', of: (module) => module.toolchains },
];

const SORTS = [
  { id: 'name', label: 'Name' },
  { id: 'type', label: 'Module type' },
  { id: 'version', label: 'Version' },
];

const searchText = (module: CatalogModule) =>
  [
    module.name,
    module.summary,
    module.type,
    module.version,
    ...module.capabilities,
    ...module.socs,
    ...module.boards,
    ...module.toolchains,
  ]
    .join(' ')
    .toLowerCase();

const list = (values: string[]) => (values.length ? values.join(', ') : '—');

/* The wildcard is a statement, not a target: it reads as a word in a cell and
   as nothing in a dropdown. */
const show = (values: string[], wildcard: string) =>
  list(values.map((value) => (value === wildcard ? 'any' : value)));

function Facet({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  const id = React.useId();
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span id={id} className="text-label text-muted-foreground uppercase">
        {label}
      </span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger size="sm" aria-labelledby={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        {/* The board list is seventeen long and the capability list longer, so
            the popover scrolls rather than running off the viewport. */}
        <SelectContent className="max-h-72">
          <SelectItem value={ANY}>Any</SelectItem>
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export default function ModuleBrowser({ modules, wildcard = '*' }: ModuleBrowserProps) {
  const [query, setQuery] = React.useState('');
  const [selected, setSelected] = React.useState<Record<FacetId, string>>({
    type: ANY,
    soc: ANY,
    board: ANY,
    toolchain: ANY,
    capability: ANY,
  });
  const [sort, setSort] = React.useState('name');


  /* The field stays immediate while the table catches up behind it. */
  const deferredQuery = React.useDeferredValue(query);

  const haystack = React.useMemo(() => modules.map(searchText), [modules]);

  const options = React.useMemo(() => {
    const found = {} as Record<FacetId, string[]>;
    for (const facet of FACETS) {
      const values = new Set<string>();
      for (const module of modules) {
        for (const value of facet.of(module)) {
          if (value && value !== wildcard) values.add(value);
        }
      }
      found[facet.id] = [...values].sort((a, b) =>
        a.localeCompare(b, undefined, { numeric: true }),
      );
    }
    return found;
  }, [modules, wildcard]);

  const visible = React.useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase();
    const rows = modules.filter((module, index) => {
      if (needle && !needle.split(/\s+/).every((word) => haystack[index].includes(word))) return false;
      return FACETS.every((facet) => {
        const wanted = selected[facet.id];
        if (wanted === ANY) return true;
        const declared = facet.of(module);
        /* A manifest that declares every target of a kind answers every
           selection of that kind; that is what the wildcard means. */
        return declared.includes(wanted) || declared.includes(wildcard);
      });
    });
    return [...rows].sort((a, b) => {
      if (sort === 'type') return a.type.localeCompare(b.type) || a.name.localeCompare(b.name);
      if (sort === 'version') {
        return (
          b.version.localeCompare(a.version, undefined, { numeric: true }) ||
          a.name.localeCompare(b.name)
        );
      }
      return a.name.localeCompare(b.name);
    });
  }, [modules, haystack, deferredQuery, selected, sort, wildcard]);

  const filtered = query.trim().length > 0 || FACETS.some((f) => selected[f.id] !== ANY);

  const clear = () => {
    setQuery('');
    setSelected({ type: ANY, soc: ANY, board: ANY, toolchain: ANY, capability: ANY });
  };

  return (
    <div data-slot="module-browser" className="not-content nsx-catalog">
      <aside className="nsx-catalog-filters" aria-label="Filter modules">
        <h2 className="text-base font-semibold">Filter modules</h2>
        {FACETS.map((facet) => (
          <Facet key={facet.id} label={facet.label} value={selected[facet.id]}
            options={options[facet.id]}
            onChange={(value) => setSelected((current) => ({ ...current, [facet.id]: value }))} />
        ))}
        <Button type="button" variant="outline" size="sm" onClick={clear} disabled={!filtered}>Clear filters</Button>
      </aside>
      <div className="min-w-0 flex flex-col gap-4">
        <label htmlFor="module-search" className="text-sm font-medium">Search modules</label>
        <Input id="module-search" type="search" value={query}
          placeholder="Name, capability or target…" onChange={(event) => setQuery(event.target.value)} />
        <div className="flex items-center justify-between gap-3">
          <p role="status" aria-live="polite" className="text-sm text-muted-foreground">{visible.length} of {modules.length} modules</p>
          <Select value={sort} onValueChange={setSort}>
            <SelectTrigger size="sm" aria-label="Sort modules"><SelectValue /></SelectTrigger>
            <SelectContent>{SORTS.map((option) => <SelectItem key={option.id} value={option.id}>{option.label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        {visible.length === 0 ? <p>No modules match. Try fewer filters or a broader search.</p> :
          <div className="flex flex-col gap-3">{visible.map((module) => (
            <article key={module.name} data-slot="module-row" className="rounded-lg border p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <a href={module.href} className="font-semibold underline-offset-4 hover:underline break-all">{module.name}</a>
                <span className="text-xs text-muted-foreground">{module.type}</span>
              </div>
              <p className="mt-2 text-sm">{module.summary}</p>
              <details className="mt-3 text-sm">
                <summary className="cursor-pointer text-muted-foreground">Compatibility and dependencies</summary>
                <dl className="mt-3 grid gap-2 break-words">
                  <dt>Boards</dt><dd>{show(module.boards, wildcard)}</dd>
                  <dt>SoCs</dt><dd>{show(module.socs, wildcard)}</dd>
                  <dt>Toolchains</dt><dd>{show(module.toolchains, wildcard)}</dd>
                  <dt>Capabilities</dt><dd>{list(module.capabilities)}</dd>
                  <dt>Required modules</dt><dd>{list(module.depends.required)}</dd>
                  <dt>Optional modules</dt><dd>{list(module.depends.optional)}</dd>
                  <dt>Version</dt><dd>{module.version || '—'}</dd>
                </dl>
              </details>
            </article>
          ))}</div>}
      </div>
    </div>
  );
}
