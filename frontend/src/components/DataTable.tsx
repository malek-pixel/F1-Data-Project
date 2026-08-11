import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  /** Right-aligned tabular figures. Use for anything compared down a column. */
  numeric?: boolean;
  /** Sort key sent to the API. Omit to make the column unsortable. */
  sortKey?: string;
  render: (row: T) => ReactNode;
}

/**
 * Table with server-driven sorting.
 *
 * Sorting is a request, not a client-side array sort: the backend holds the
 * full result set and the client only ever has the current page, so sorting
 * locally would sort the page rather than the data.
 *
 * `aria-sort` is set on the active column so screen readers announce the
 * current order.
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
    return (
      <p style={{ color: "var(--text-dim)", fontSize: 13, padding: "16px 0" }}>{emptyMessage}</p>
    );
  }
  return (
    <div className="table-scroll">
      <table className="data">
        <caption
          style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}
        >
          {caption}
        </caption>
        <thead>
          <tr>
            {columns.map((column) => {
              const active = Boolean(column.sortKey && sort === column.sortKey);
              return (
                <th
                  key={column.key}
                  className={column.numeric ? "num" : undefined}
                  scope="col"
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
                      <span aria-hidden="true">{active ? "▾" : ""}</span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td key={column.key} className={column.numeric ? "num" : undefined}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
