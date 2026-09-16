import { useEffect, useState, useCallback } from 'react';
import { Search, ChevronLeft, ChevronRight, ArrowUpDown, Download } from 'lucide-react';
import { Button, Spinner, EmptyState } from './ui';
import type { ResultsPage } from '../types';

export function DataTable({
  fetcher,
  onExport,
  onRowClick,
  emptyLabel = 'No records found',
  keyColumn,
}: {
  fetcher: (params: { page: number; page_size: number; search?: string; sort_by?: string; sort_dir?: string }) => Promise<ResultsPage>;
  onExport?: () => void;
  onRowClick?: (row: Record<string, unknown>) => void;
  emptyLabel?: string;
  keyColumn?: string;
}) {
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [sortBy, setSortBy] = useState<string | undefined>();
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [data, setData] = useState<ResultsPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => setPage(1), [debouncedSearch]);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetcher({ page, page_size: pageSize, search: debouncedSearch || undefined, sort_by: sortBy, sort_dir: sortDir })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [fetcher, page, pageSize, debouncedSearch, sortBy, sortDir]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  const toggleSort = (col: string) => {
    if (sortBy === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(col);
      setSortDir('asc');
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3 gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search records..."
            className="w-full pl-8 pr-3 py-1.5 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-(--color-brand-600)"
          />
        </div>
        <div className="flex items-center gap-2">
          {data && <span className="text-sm text-slate-500">{data.total.toLocaleString()} records</span>}
          {onExport && (
            <Button variant="secondary" onClick={onExport}>
              <Download className="h-3.5 w-3.5" /> Export CSV
            </Button>
          )}
        </div>
      </div>

      {error && <div className="text-red-700 bg-red-50 border border-red-200 rounded-md p-3 text-sm mb-3">{error}</div>}

      <div className="overflow-x-auto border border-slate-200 rounded-lg">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              {data?.columns.map((col) => (
                <th
                  key={col}
                  onClick={() => toggleSort(col)}
                  className="text-left px-3 py-2 font-medium text-slate-600 whitespace-nowrap cursor-pointer select-none hover:bg-slate-100"
                >
                  <span className="inline-flex items-center gap-1">
                    {col}
                    <ArrowUpDown className={`h-3 w-3 ${sortBy === col ? 'text-(--color-brand-600)' : 'text-slate-300'}`} />
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr>
                <td colSpan={data?.columns.length || 1} className="text-center py-10">
                  <Spinner className="mx-auto text-(--color-brand-600)" />
                </td>
              </tr>
            )}
            {!loading && data && data.rows.length === 0 && (
              <tr>
                <td colSpan={data.columns.length || 1}>
                  <EmptyState title={emptyLabel} />
                </td>
              </tr>
            )}
            {!loading &&
              data?.rows.map((row, i) => (
                <tr
                  key={keyColumn ? String(row[keyColumn]) + i : i}
                  onClick={() => onRowClick?.(row)}
                  className={`hover:bg-slate-50 ${onRowClick ? 'cursor-pointer' : ''}`}
                >
                  {data.columns.map((col) => (
                    <td key={col} className="px-3 py-2 whitespace-nowrap text-slate-700">
                      {row[col] === null || row[col] === undefined ? (
                        <span className="text-slate-300 italic">null</span>
                      ) : (
                        String(row[col])
                      )}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {data && data.total > 0 && (
        <div className="flex items-center justify-between mt-3 text-sm text-slate-600">
          <div>
            Page {page} of {totalPages}
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              <ChevronLeft className="h-3.5 w-3.5" /> Prev
            </Button>
            <Button variant="secondary" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
