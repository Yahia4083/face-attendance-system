import { EmptyState } from "./State";

export type Column<T> = {
  header: string;
  render: (row: T) => React.ReactNode;
  className?: string;
};

export function DataTable<T>({
  columns,
  rows,
  empty,
  emptyTitle,
  rowKey,
  caption,
}: {
  columns: Column<T>[];
  rows: T[];
  empty?: string;
  emptyTitle?: string;
  rowKey?: (row: T, index: number) => React.Key;
  caption?: string;
}) {
  if (!rows.length) return <EmptyState title={emptyTitle} description={empty ?? "Try changing filters or refreshing the page."} />;
  return (
    <div className="table-scroll rounded-md border border-slate-300 bg-white">
      <table className="min-w-full divide-y divide-slate-300 text-sm">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead className="bg-slate-100 text-left text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-slate-600">
          <tr>
            {columns.map((column) => (
              <th scope="col" key={column.header} className={`whitespace-nowrap px-3.5 py-2.5 ${column.className ?? ""}`}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200">
          {rows.map((row, index) => (
            <tr key={rowKey ? rowKey(row, index) : index} className="transition-colors hover:bg-signal-50/70">
              {columns.map((column) => (
                <td key={column.header} className={`px-3.5 py-3 align-middle text-slate-700 ${column.className ?? ""}`}>
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
