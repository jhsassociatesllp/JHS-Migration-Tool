import { useEffect, useRef, useState } from 'react';
import { Play, RefreshCw, FileSpreadsheet } from 'lucide-react';
import {
  listMappings, listRuns, startRun, getRun, getTabResults, getRecordDetail,
  exportExcelUrl, exportCsvUrl,
} from '../../api/client';
import type { MappingConfig, ValidationRun } from '../../types';
import { Card, Button, StatCard, ProgressBar, EmptyState, Spinner } from '../../components/ui';
import { DataTable } from '../../components/DataTable';

const TABS = [
  { key: 'missing', label: 'Missing' },
  { key: 'extra', label: 'Extra' },
  { key: 'changed', label: 'Changed' },
  { key: 'field_diffs', label: 'Field Differences' },
  { key: 'duplicates_source', label: 'Duplicates (Source)' },
  { key: 'duplicates_target', label: 'Duplicates (Target)' },
] as const;

export function ValidationTab({ projectId }: { projectId: string }) {
  const [mappings, setMappings] = useState<MappingConfig[]>([]);
  const [runs, setRuns] = useState<ValidationRun[]>([]);
  const [selectedMappingId, setSelectedMappingId] = useState('');
  const [activeRun, setActiveRun] = useState<ValidationRun | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]['key']>('missing');
  const [detail, setDetail] = useState<any>(null);
  const pollRef = useRef<number | null>(null);

  const load = async () => {
    const [ms, rs] = await Promise.all([listMappings(projectId), listRuns(projectId)]);
    setMappings(ms);
    setRuns(rs);
    if (ms.length && !selectedMappingId) setSelectedMappingId(ms[0].id);
    if (rs.length && !activeRun) setActiveRun(rs[0]);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    if (activeRun && (activeRun.status === 'queued' || activeRun.status === 'running')) {
      pollRef.current = window.setInterval(async () => {
        const updated = await getRun(projectId, activeRun.id);
        setActiveRun(updated);
        if (updated.status === 'completed' || updated.status === 'failed') {
          if (pollRef.current) window.clearInterval(pollRef.current);
          setRuns((rs) => [updated, ...rs.filter((r) => r.id !== updated.id)]);
        }
      }, 800);
    }
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRun?.id, activeRun?.status]);

  const run = async () => {
    if (!selectedMappingId) return;
    const r = await startRun(projectId, selectedMappingId);
    setRuns((rs) => [r, ...rs]);
    setActiveRun(r);
  };

  const openRecord = async (row: Record<string, unknown>) => {
    if (!activeRun) return;
    const key = (row['matching_key'] ?? row['OBCustomerNo'] ?? row['custid']) as string | undefined;
    if (key === undefined) return;
    const d = await getRecordDetail(projectId, activeRun.id, String(key));
    setDetail(d);
  };

  if (mappings.length === 0) {
    return (
      <Card>
        <EmptyState title="No mapping configured yet" subtitle="Go to the Mapping tab and save a column mapping before running validation." />
      </Card>
    );
  }

  const s = activeRun?.summary_json || {};

  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="flex items-center gap-3 flex-wrap">
          <select
            value={selectedMappingId}
            onChange={(e) => setSelectedMappingId(e.target.value)}
            className="border border-slate-300 rounded-md px-3 py-2 text-sm"
          >
            {mappings.map((m) => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
          <Button onClick={run} disabled={!!activeRun && (activeRun.status === 'queued' || activeRun.status === 'running')}>
            <Play className="h-3.5 w-3.5" /> Run Validation
          </Button>
          {runs.length > 0 && (
            <select
              value={activeRun?.id || ''}
              onChange={(e) => setActiveRun(runs.find((r) => r.id === e.target.value) || null)}
              className="border border-slate-300 rounded-md px-3 py-2 text-sm ml-auto"
            >
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  Run {new Date(r.started_at).toLocaleString()} — {r.status}
                </option>
              ))}
            </select>
          )}
        </div>

        {activeRun && (activeRun.status === 'queued' || activeRun.status === 'running') && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-sm mb-1">
              <span className="text-slate-600 flex items-center gap-2">
                <Spinner className="text-(--color-brand-600)" /> {activeRun.current_operation || 'Starting...'}
              </span>
              <span className="text-slate-500">{activeRun.progress_percent}%</span>
            </div>
            <ProgressBar percent={activeRun.progress_percent} />
          </div>
        )}

        {activeRun?.status === 'failed' && (
          <div className="mt-4 text-red-700 bg-red-50 border border-red-200 rounded-md p-3 text-sm">{activeRun.error_message}</div>
        )}
      </Card>

      {activeRun?.status === 'completed' && (
        <>
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-medium text-slate-800">Migration Validation Summary</h2>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => setActiveRun({ ...activeRun })}>
                  <RefreshCw className="h-3.5 w-3.5" /> Refresh
                </Button>
                <a href={exportExcelUrl(projectId, activeRun.id)}>
                  <Button variant="secondary">
                    <FileSpreadsheet className="h-3.5 w-3.5" /> Export Full Report (Excel)
                  </Button>
                </a>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard label="Source Records" value={s.source_rows ?? 0} />
              <StatCard label="Target Records" value={s.target_rows ?? 0} />
              <StatCard label="Matched" value={s.matched ?? 0} tone="good" />
              <StatCard label="Missing in Target" value={s.missing ?? 0} tone={s.missing ? 'bad' : 'default'} />
              <StatCard label="Extra in Target" value={s.extra ?? 0} tone={s.extra ? 'warn' : 'default'} />
              <StatCard label="Changed" value={s.changed ?? 0} tone={s.changed ? 'warn' : 'default'} />
              <StatCard label="Duplicate Keys (Source)" value={s.duplicates_in_source ?? 0} tone={s.duplicates_in_source ? 'bad' : 'default'} />
              <StatCard label="Duplicate Keys (Target)" value={s.duplicates_in_target ?? 0} tone={s.duplicates_in_target ? 'bad' : 'default'} />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
              <StatCard label="Unique Source Customers" value={s.unique_source_customers ?? 0} />
              <StatCard label="Unique Target Customers" value={s.unique_target_customers ?? 0} />
              <StatCard label="Blank Key Rows (Source)" value={s.source_rows_with_null_key ?? 0} />
              <StatCard label="Blank Key Rows (Target)" value={s.target_rows_with_null_key ?? 0} />
            </div>
            {activeRun.duration_seconds !== null && (
              <div className="text-xs text-slate-400 mt-2">Completed in {activeRun.duration_seconds?.toFixed(1)}s</div>
            )}
          </div>

          <div>
            <h2 className="font-medium text-slate-800 mb-3">Difference Explorer</h2>
            <div className="flex gap-1 border-b border-slate-200 mb-4 overflow-x-auto">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`px-3 py-2 text-sm whitespace-nowrap border-b-2 -mb-px ${
                    tab === t.key ? 'border-(--color-brand-600) text-(--color-brand-600) font-medium' : 'border-transparent text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {t.label} <span className="text-xs text-slate-400">({s[`${t.key === 'field_diffs' ? 'changed' : t.key}`.replace('duplicates_source', 'duplicates_in_source').replace('duplicates_target', 'duplicates_in_target')] ?? ''})</span>
                </button>
              ))}
            </div>
            <DataTable
              key={`${activeRun.id}-${tab}`}
              fetcher={(params) => getTabResults(projectId, activeRun.id, tab, params)}
              onExport={() => window.open(exportCsvUrl(projectId, activeRun.id, tab), '_blank')}
              onRowClick={openRecord}
              keyColumn="matching_key"
            />
          </div>
        </>
      )}

      {detail && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-6" onClick={() => setDetail(null)}>
          <div className="bg-white rounded-lg max-w-3xl w-full max-h-[85vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
            <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between sticky top-0 bg-white">
              <div className="font-medium text-slate-800">Record: {detail.matching_key}</div>
              <button onClick={() => setDetail(null)} className="text-slate-400 hover:text-slate-700">✕</button>
            </div>
            <div className="p-5 space-y-4">
              {detail.ambiguous && (
                <div className="text-amber-700 bg-amber-50 border border-amber-200 rounded p-2 text-sm">
                  This key has multiple rows on one or both sides (duplicate key) — field-level comparison is skipped for ambiguous matches.
                </div>
              )}
              {detail.field_comparison?.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-slate-700 mb-2">Field Comparison</h3>
                  <table className="w-full text-sm border border-slate-200 rounded overflow-hidden">
                    <thead className="bg-slate-50">
                      <tr>
                        <th className="text-left px-3 py-1.5">Field</th>
                        <th className="text-left px-3 py-1.5">Source</th>
                        <th className="text-left px-3 py-1.5">Target</th>
                        <th className="text-left px-3 py-1.5">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {detail.field_comparison.map((r: any) => (
                        <tr key={r.field}>
                          <td className="px-3 py-1.5">{r.field}</td>
                          <td className="px-3 py-1.5">{r.source_value ?? <span className="text-slate-300 italic">null</span>}</td>
                          <td className="px-3 py-1.5">{r.target_value ?? <span className="text-slate-300 italic">null</span>}</td>
                          <td className="px-3 py-1.5">
                            {r.status === 'MATCH' ? <span className="text-emerald-600">✓ MATCH</span> : <span className="text-red-600">✕ {r.status}</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <h3 className="text-sm font-medium text-slate-700 mb-2">Source Record{detail.source_records.length !== 1 ? 's' : ''}</h3>
                  <pre className="bg-slate-50 border border-slate-200 rounded p-3 text-xs overflow-auto max-h-64">
                    {JSON.stringify(detail.source_records, null, 2)}
                  </pre>
                </div>
                <div>
                  <h3 className="text-sm font-medium text-slate-700 mb-2">Target Record{detail.target_records.length !== 1 ? 's' : ''}</h3>
                  <pre className="bg-slate-50 border border-slate-200 rounded p-3 text-xs overflow-auto max-h-64">
                    {JSON.stringify(detail.target_records, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
