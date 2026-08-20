import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  /** Right-aligned tabular figures. Use for anything compared down a column. */
  numeric?: boolean;
  /** Sort key sent to the API. Omit to make the column unsortable. */
  sortKey?: string;
  /** Track width. Defaults to 80px for numeric columns, 1fr otherwise. */
  width?: string;
  /** `index` is the row's position on the current page -- used for rank columns. */
  render: (row: T, index: number) => ReactNode;
}

/**
 * Row list with server-driven sorting.
 *
 * The mockup never uses a `<table>` element: every listing in
 * `design/F1 Dashboard.dc.html` is a CSS grid whose columns are fixed px
 * tracks with one `1fr` name column (§ 03 drivers, § 06 races, § 07 seasons
 * all share the shape). This renders that grid and carries the table
 * semantics through ARIA, so the design's density survives without costing
 * screen-reader users the row/column relationships a real table gives them.
 *
 * Sorting is a request, not a client-side array sort: the backend holds the
 * full result set and the client only ever has the current page, so sorting
 * locally would sort the page rather than the data.
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  sort,
  onSort,
  emptyMessage = "No rows match these filters.",
}: {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  sort?: string;
  onSort?: (key: string) => void;
  emptyMessage?: string;
}) {
  if (rows.length === 0) {
    return <p className="table-empty">{emptyMessage}</p>;
  }

  // One template drives the header and every row, so columns stay aligned
  // without each cell knowing its own width.
  //
  // The mockup's listings are fixed px tracks with a single `1fr` name
  // column. Giving every text column `1fr` instead makes each one claim an
  // equal share, and a nine-column table then measures far wider than the
  // pane: the races listing came out at 2716px inside 1143px. So only the
  // first text column flexes; later ones take their content width.
  // Floors matter as much as the flex: without them a column of "—" placeholder
  // cells collapses to ~20px and its header is unreadable.
  let flexed = false;
  const track = (c: Column<T>) => {
    if (c.width) return c.width;
    if (c.numeric) return "minmax(56px, max-content)";
    if (!flexed) {
      flexed = true;
      return "minmax(140px, 1fr)";
    }
    return "minmax(72px, max-content)";
  };
  const template = columns.map(track).join(" ");

  return (
    <div className="table-scroll">
      <div className="rows" role="table" aria-label={caption} style={{ ["--cols" as string]: template }}>
        <div className="rows__head mono" role="row">
          {columns.map((column) => {
            const active = Boolean(column.sortKey && sort === column.sortKey);
            return (
              <span
                key={column.key}
                role="columnheader"
                className={column.numeric ? "num" : undefined}
                aria-sort={active ? "descending" : column.sortKey ? "none" : undefined}
              >
                {column.sortKey && onSort ? (
                  <button
                    className="sort-btn"
                    data-active={active}
                    onClick={() => onSort(column.sortKey!)}
                    aria-label={`Sort by ${column.header}`}
                  >
                    {column.header}
                    {/* Always rendered, so revealing it on hover cannot shift
                        the header's layout. Visibility is CSS-only. */}
                    <span className="sort-btn__caret" aria-hidden="true">
                      ▾
                    </span>
                  </button>
                ) : (
                  column.header
                )}
              </span>
            );
          })}
        </div>
        {rows.map((row, index) => (
          <div className="rows__row" role="row" key={rowKey(row)}>
            {columns.map((column) => (
              <span role="cell" key={column.key} className={column.numeric ? "num" : undefined}>
                {column.render(row, index)}
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
