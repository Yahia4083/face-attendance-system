import { Button } from "./Button";

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const lastPage = Math.max(1, Math.ceil(total / pageSize));
  const firstItem = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastItem = Math.min(total, page * pageSize);
  return (
    <nav className="mt-3 flex flex-col gap-3 border-t border-slate-200 pt-3 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between" aria-label="Pagination">
      <span aria-live="polite">
        Showing {firstItem}-{lastItem} of {total} records
      </span>
      <div className="flex gap-2">
        <span className="inline-flex min-h-8 items-center border-x border-slate-200 px-3 text-xs font-medium text-slate-600">Page {page} of {lastPage}</span>
        <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPageChange(page - 1)} aria-label="Go to previous page">
          Previous
        </Button>
        <Button size="sm" variant="secondary" disabled={page >= lastPage} onClick={() => onPageChange(page + 1)} aria-label="Go to next page">
          Next
        </Button>
      </div>
    </nav>
  );
}

