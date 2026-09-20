// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/*
 * The module catalog's toolbar: a search field, one dropdown per declared
 * facet, a sort order, and the results as a table.
 *
 * The package has no catalog filter. `RefIndex` is the one faceted control it
 * ships and it renders every value of every facet as a chip, which for fifty
 * modules over seventeen boards and a hundred capabilities is a wall of chips
 * above the answer. So this is assembled from the package's own primitives --
 * `Input`, `Select`, `Button` and the table parts -- with Tailwind utilities
 * for layout and nothing of its own to style. See
 * tasks/256-docs-migration/helia-ui-gaps-259.md.
 *
 * Rows arrive built from the committed snapshot, which is the same file the
 * static table on the page is generated from, so the two cannot disagree
 * (AmbiqAI/neuralspotx#259).
 */
import * as React from 'react';
import { ChevronDownIcon, ChevronRightIcon } from 'lucide-react';
import { Button } from '@ambiqai/helia-ui/react/button';
import { Input } from '@ambiqai/helia-ui/react/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@ambiqai/helia-ui/react/select';
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@ambiqai/helia-ui/react/table';

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

type FacetId = 'type' | 'soc' | 'board' | 'toolchain';

const FACETS: { id: FacetId; label: string; of: (module: CatalogModule) => string[] }[] = [
  { id: 'type', label: 'Type', of: (module) => [module.type] },
  { id: 'soc', label: 'SoC', of: (module) => module.socs },
  { id: 'board', label: 'Board', of: (module) => module.boards },
  { id: 'toolchain', label: 'Toolchain', of: (module) => module.toolchains },
];

const COLUMNS = [
  { label: 'Module', width: 'w-[22%]' },
  { label: 'Type', width: 'w-[14%]' },
  { label: 'Summary', width: 'w-[44%]' },
  { label: 'Boards', width: 'w-[20%]' },
];

const SORTS = [
  { id: 'name', label: 'Name' },
  { id: 'type', label: 'Type' },
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
  });
  const [sort, setSort] = React.useState('name');
  const [expanded, setExpanded] = React.useState<string[]>([]);

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
      if (needle && !haystack[index].includes(needle)) return false;
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
    setSelected({ type: ANY, soc: ANY, board: ANY, toolchain: ANY });
  };

  const toggle = (name: string) =>
    setExpanded((current) =>
      current.includes(name) ? current.filter((entry) => entry !== name) : [...current, name],
    );

  return (
    <div data-slot="module-browser" className="not-content flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
        <div className="flex flex-col gap-1 sm:col-span-2">
          <label id="module-search-label" className="text-label text-muted-foreground uppercase">
            Search
          </label>
          <Input
            type="search"
            value={query}
            aria-labelledby="module-search-label"
            placeholder="Name, summary, capability or target"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        {FACETS.map((facet) => (
          <Facet
            key={facet.id}
            label={facet.label}
            value={selected[facet.id]}
            options={options[facet.id]}
            onChange={(value) => setSelected((current) => ({ ...current, [facet.id]: value }))}
          />
        ))}
        <div className="flex min-w-0 flex-col gap-1">
          <span id="module-sort-label" className="text-label text-muted-foreground uppercase">
            Sort
          </span>
          <Select value={sort} onValueChange={setSort}>
            <SelectTrigger size="sm" aria-labelledby="module-sort-label" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SORTS.map((option) => (
                <SelectItem key={option.id} value={option.id}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3">
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {visible.length} of {modules.length} modules
        </p>
        {filtered && (
          <Button type="button" variant="ghost" size="sm" onClick={clear}>
            Clear filters
          </Button>
        )}
      </div>

      {visible.length === 0 ? (
        <p className="rounded-md border p-4 text-sm text-muted-foreground">
          No modules match these filters.
        </p>
      ) : (
        <div className="max-h-[36rem] overflow-y-auto rounded-md border">
          <Table>
            <TableCaption className="sr-only">Modules matching these filters</TableCaption>
            <TableHeader>
              <TableRow>
                {/* Four columns fit the content width with the sidebar in
                    place. What a module declares beyond its boards is a row
                    the reader opens, not a column they scroll to. The widths
                    are hints: left to itself the table gives the name column
                    the space and wraps the summary into a ribbon. */}
                {COLUMNS.map((column) => (
                  <TableHead
                    key={column.label}
                    className={`sticky top-0 bg-background ${column.width}`}
                  >
                    {column.label}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((module) => {
                const open = expanded.includes(module.name);
                const detailId = `${module.name}-detail`;
                return (
                  <React.Fragment key={module.name}>
                    <TableRow data-slot="module-row">
                      <TableCell className="align-top font-medium whitespace-nowrap">
                        <span className="flex items-center gap-1">
                          <button
                            type="button"
                            aria-expanded={open}
                            aria-controls={detailId}
                            aria-label={`What ${module.name} declares`}
                            onClick={() => toggle(module.name)}
                            className="inline-flex size-5 items-center justify-center rounded-sm text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                          >
                            {open ? (
                              <ChevronDownIcon className="size-4" />
                            ) : (
                              <ChevronRightIcon className="size-4" />
                            )}
                          </button>
                          <a
                            href={module.href}
                            className="font-mono text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                          >
                            {module.name}
                          </a>
                        </span>
                      </TableCell>
                      <TableCell className="align-top whitespace-nowrap">{module.type}</TableCell>
                      {/* The table part sets whitespace-nowrap on every cell,
                          and `cn` merges Tailwind classes, so wrapping is asked
                          for rather than fought with a width. */}
                      <TableCell className="align-top whitespace-normal text-muted-foreground">
                        {module.summary}
                      </TableCell>
                      <TableCell className="align-top text-sm whitespace-normal">
                        {show(module.boards, wildcard)}
                      </TableCell>
                    </TableRow>
                    {open && (
                      <TableRow data-slot="module-detail" id={detailId}>
                        <TableCell colSpan={4} className="bg-muted/40 whitespace-normal">
                          <dl className="grid gap-2 text-sm md:grid-cols-[10rem_1fr]">
                            <dt className="text-muted-foreground">Version</dt>
                            <dd>{module.version || '—'}</dd>
                            <dt className="text-muted-foreground">SoCs</dt>
                            <dd>{show(module.socs, wildcard)}</dd>
                            <dt className="text-muted-foreground">Toolchains</dt>
                            <dd>{show(module.toolchains, wildcard)}</dd>
                            {module.capabilities.length > 0 && (
                              <>
                                <dt className="text-muted-foreground">Capabilities</dt>
                                <dd>{list(module.capabilities)}</dd>
                              </>
                            )}
                            {module.depends.required.length > 0 && (
                              <>
                                <dt className="text-muted-foreground">Requires</dt>
                                <dd>{list(module.depends.required)}</dd>
                              </>
                            )}
                            {module.depends.optional.length > 0 && (
                              <>
                                <dt className="text-muted-foreground">Optional</dt>
                                <dd>{list(module.depends.optional)}</dd>
                              </>
                            )}
                          </dl>
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
