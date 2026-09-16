import { useEffect, useState } from 'react';
import { listRuns, compareRuns } from '../../api/client';
import type { ValidationRun } from '../../types';
import { Card, StatusBadge, EmptyState, Button } from '../../components/ui';

export function HistoryTab({ projectId }: { projectId: string }) {
  const [runs, setRuns] = useState<ValidationRun[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<any>(null);

  useEffect(() => {
    listRuns(projectId).then(setRuns);
  }, [projectId]);

  const toggleSelect = (id: string) => {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length < 2 ? [...s, id] : [s[1], id]));
    setComparison(null);
  };

  const doCompare = async () => {
    if (selected.length !== 2) return;
    const [a, b] = selected;
    const runA = runs.find((r) => r.id === a)!;
    const runB = runs.find((r) => r.id === b)!;
    const [older, newer] = new Date(runA.started_at) < new Date(runB.started_at) ? [runA, runB] : [runB, runA];
    const res = await compareRuns(projectId, older.id, newer.id);
    setComparison(res);
  };

  if (runs.length === 0) {
    return (
      <Card>
        <EmptyState title="No validation runs yet" subtitle="Run a validation from the Validation tab to see history here." />
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-500">Select two runs to compare their summaries.</div>
        <Button variant="secondary" disabled={selected.length !== 2} onClick={doCompare}>
          Compare Selected Runs
        </Button>
      </div>

      <div className="space-y-2">
        {runs.map((r) => (
          <Card key={r.id} className={`p-4 flex items-center gap-4 ${selected.includes(r.id) ? 'ring-2 ring-(--color-brand-600)' : ''}`}>
            <input type="checkbox" checked={selected.includes(r.id)} onChange={() => toggleSelect(r.id)} />
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-slate-800">{new Date(r.started_at).toLocaleString()}</span>
                <StatusBadge status={r.status} />
              </div>
              {r.status === 'completed' && (
                <div className="text-xs text-slate-500 mt-1 flex gap-4 flex-wrap">
                  <span>Source: {r.summary_json.source_rows?.toLocaleString()}</span>
                  <span>Target: {r.summary_json.target_rows?.toLocaleString()}</span>
                  <span>Missing: {r.summary_json.missing?.toLocaleString()}</span>
                  <span>Extra: {r.summary_json.extra?.toLocaleString()}</span>
                  <span>Changed: {r.summary_json.changed?.toLocaleString()}</span>
                  <span>Duration: {r.duration_seconds?.toFixed(1)}s</span>
                </div>
              )}
              {r.status === 'failed' && <div className="text-xs text-red-600 mt-1">{r.error_message}</div>}
            </div>
          </Card>
        ))}
      </div>

      {comparison && (
        <Card className="p-5">
          <h2 className="font-medium text-slate-800 mb-3">Run Comparison</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200">
                <th className="py-1.5">Metric</th>
                <th className="py-1.5">Earlier Run</th>
                <th className="py-1.5">Later Run</th>
                <th className="py-1.5">Change</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {Object.entries(comparison.diff).map(([k, v]: [string, any]) => (
                <tr key={k}>
                  <td className="py-1.5 text-slate-600">{k.replace(/_/g, ' ')}</td>
                  <td className="py-1.5">{v.run_a}</td>
                  <td className="py-1.5">{v.run_b}</td>
                  <td className={`py-1.5 font-medium ${v.delta > 0 ? 'text-amber-600' : v.delta < 0 ? 'text-emerald-600' : 'text-slate-400'}`}>
                    {v.delta > 0 ? `+${v.delta}` : v.delta}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
