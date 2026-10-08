export interface Column<T> {
  key: string;
  header: string;
  numeric?: boolean;
  render: (row: T) => React.ReactNode;
}

export function DataTable<T extends { symbol?: string } | Record<string, unknown>>({
  columns,
  rows,
  caption,
}: {
  columns: Column<T>[];
  rows: T[];
  caption: string;
}) {
  return (
    <div className="v2-table-wrapper">
      <table className="v2-table" data-testid="data-table">
        <caption className="v2-muted" style={{ textAlign: "left" }}>
          {caption}
        </caption>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} scope="col">
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={String((row as { symbol?: unknown }).symbol ?? i)}>
              {columns.map((col) => (
                <td key={col.key}>{col.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function FilterTabs({
  tabs,
  active,
  onChange,
}: {
  tabs: string[];
  active: string;
  onChange: (tab: string) => void;
}) {
  return (
    <div className="v2-tabs" role="tablist" aria-label="Filters" data-testid="filter-tabs">
      {tabs.map((tab) => (
        <button
          key={tab}
          role="tab"
          aria-selected={tab === active}
          className="v2-chip"
          data-tone={tab === active ? "info" : "muted"}
          onClick={() => onChange(tab)}
          type="button"
        >
          {tab}
        </button>
      ))}
    </div>
  );
}
