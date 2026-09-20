// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/*
 * The catalog's filter controls.
 *
 * The table itself is not here. The catalog page renders every module as an
 * ordinary Markdown table, which is what Pagefind indexes, what the Markdown
 * rendition carries and what a reader without JavaScript gets; this island
 * only hides rows in that table. Rendering the rows here as well would put
 * fifty modules on the page twice, and mounting the island with `client:only`
 * means the controls never appear without the script that makes them work.
 *
 * Rows are matched to their facet values by the module name in the first cell,
 * which the generator writes on both sides of the pair. Free text is searched
 * against the row's own text, so the summary does not have to cross into the
 * props a second time.
 *
 * helia-ui has no faceted filter to use instead: the Astro `DataTable` takes
 * string cells and no filter, and the React `RefIndex` island is typed to
 * reference symbols. See tasks/256-docs-migration/helia-ui-gaps-259.md.
 */
import * as React from 'react';

export interface CatalogFacet {
  id: string;
  label: string;
  values: string[];
  /** Set by the generator when a facet has too many values for one row of chips. */
  collapsed?: boolean;
}

export interface ModuleCatalogFilterProps {
  facets: CatalogFacet[];
  /** Module name to facet id to the values that module declares. */
  rows: Record<string, Record<string, string[]>>;
  /** id of the element wrapping the static table this filters. */
  tableId: string;
  /** The value a manifest uses to declare every target, matched by any selection. */
  wildcard?: string;
}

interface Row {
  element: HTMLTableRowElement;
  name: string;
  text: string;
}

const EMPTY: string[] = [];

function matches(
  values: string[] | undefined,
  selected: string[],
  wildcard: string,
): boolean {
  if (selected.length === 0) return true;
  if (!values || values.length === 0) return false;
  if (values.includes(wildcard)) return true;
  return selected.some((value) => values.includes(value));
}

export default function ModuleCatalogFilter({
  facets,
  rows,
  tableId,
  wildcard = '*',
}: ModuleCatalogFilterProps) {
  /* A link may arrive with a selection already made, which is how the overview
     page's type cards land on a catalog filtered to one type. */
  const [selected, setSelected] = React.useState<Record<string, string[]>>(() => {
    if (typeof window === 'undefined') return {};
    const params = new URLSearchParams(window.location.search);
    const initial: Record<string, string[]> = {};
    for (const facet of facets) {
      const values = params.getAll(facet.id).filter((value) => facet.values.includes(value));
      if (values.length) initial[facet.id] = values;
    }
    return initial;
  });
  const [query, setQuery] = React.useState('');
  const [tableRows, setTableRows] = React.useState<Row[]>([]);

  React.useEffect(() => {
    const container = document.getElementById(tableId);
    if (!container) return;
    const found = Array.from(container.querySelectorAll('tbody tr')).map((element) => {
      const row = element as HTMLTableRowElement;
      return {
        element: row,
        name: (row.cells[0]?.textContent ?? '').trim(),
        text: (row.textContent ?? '').toLowerCase(),
      };
    });
    setTableRows(found);
  }, [tableId]);

  const needle = query.trim().toLowerCase();
  const [visible, setVisible] = React.useState(0);

  /* The rows are the page's, not this component's, so hiding them is a DOM
     effect rather than a render. */
  React.useEffect(() => {
    let count = 0;
    for (const row of tableRows) {
      const declared = rows[row.name];
      const facetHit = facets.every((facet) =>
        matches(declared?.[facet.id], selected[facet.id] ?? EMPTY, wildcard),
      );
      const textHit = needle === '' || row.text.includes(needle);
      const show = facetHit && textHit;
      row.element.hidden = !show;
      if (show) count += 1;
    }
    setVisible(count);
  }, [tableRows, rows, facets, selected, needle, wildcard]);

  const active = facets.reduce((total, facet) => total + (selected[facet.id]?.length ?? 0), 0);

  const toggle = (facetId: string, value: string) => {
    setSelected((current) => {
      const values = current[facetId] ?? EMPTY;
      const next = values.includes(value)
        ? values.filter((item) => item !== value)
        : [...values, value];
      return { ...current, [facetId]: next };
    });
  };

  return (
    <div className="not-content mb-6 flex flex-col gap-4">
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-semibold">Search the catalog</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="name, summary, capability or keyword"
          className="w-full max-w-md rounded border border-[var(--sl-color-gray-5)] bg-[var(--sl-color-black)] px-3 py-2 text-[var(--sl-color-white)]"
        />
      </label>

      {facets.map((facet) => {
        const chosen = selected[facet.id] ?? EMPTY;
        const chips = (
          <>
            {facet.values.map((value) => {
              const on = chosen.includes(value);
              return (
                <button
                  key={value}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggle(facet.id, value)}
                  className={
                    'rounded-full border px-2.5 py-0.5 text-xs transition-colors ' +
                    (on
                      ? 'border-[var(--sl-color-accent)] bg-[var(--sl-color-accent)] text-[var(--sl-color-black)]'
                      : 'border-[var(--sl-color-gray-5)] text-[var(--sl-color-gray-2)] hover:border-[var(--sl-color-accent)]')
                  }
                >
                  {value}
                </button>
              );
            })}
          </>
        );

        /* A facet with a hundred values is a list, not a row of chips, so it
           opens on demand and reports its own selection while closed. */
        if (facet.collapsed) {
          return (
            <details key={facet.id} open={chosen.length > 0}>
              <summary className="cursor-pointer text-sm font-semibold">
                {facet.label}
                {chosen.length > 0 ? ` (${chosen.length} selected)` : ` (${facet.values.length})`}
              </summary>
              <div className="mt-2 flex flex-wrap gap-2">{chips}</div>
            </details>
          );
        }

        return (
          <fieldset key={facet.id} className="flex flex-wrap items-baseline gap-2 border-0 p-0">
            <legend className="sr-only">{facet.label}</legend>
            <span className="w-28 shrink-0 text-sm font-semibold">{facet.label}</span>
            {chips}
          </fieldset>
        );
      })}

      <p className="text-sm" aria-live="polite">
        Showing {visible} of {tableRows.length} modules.{' '}
        {(active > 0 || needle !== '') && (
          <button
            type="button"
            className="underline"
            onClick={() => {
              setSelected({});
              setQuery('');
            }}
          >
            Clear filters
          </button>
        )}
      </p>
      {visible === 0 && tableRows.length > 0 && (
        <p className="text-sm">
          No module declares all of that. Clear a filter, or read the board matrix for what each
          board declares.
        </p>
      )}
    </div>
  );
}
