import { useEffect, useState } from 'react';
import { Plus, Trash2, Sparkles, KeyRound, Save, ArrowRight, AlertTriangle } from 'lucide-react';
import {
  listFiles, getMappingSuggestions, createMapping, listMappings, deleteMapping,
} from '../../api/client';
import type { UploadedFile, FieldMapping, MappingConfig, Normalization } from '../../types';
import { Card, Button, EmptyState, Spinner } from '../../components/ui';

const emptyField = (): FieldMapping => ({
  source_columns: [],
  target_column: '',
  data_type: 'string',
  transform: 'none',
  required: false,
  is_matching_key: false,
  compare_in_validation: true,
});

const defaultNorm: Normalization = {
  trim: true,
  case_insensitive: true,
  null_tokens: ['', 'NULL', 'null', 'N/A', 'n/a', 'NA', 'na', 'None'],
  numeric_normalize: true,
  date_normalize: true,
};

export function MappingTab({ projectId, onCreated }: { projectId: string; onCreated?: (m: MappingConfig) => void }) {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [mappings, setMappings] = useState<MappingConfig[]>([]);
  const [sourceFileId, setSourceFileId] = useState('');
  const [targetFileId, setTargetFileId] = useState('');
  const [mappingName, setMappingName] = useState('');
  const [fields, setFields] = useState<FieldMapping[]>([]);
  const [norm, setNorm] = useState<Normalization>(defaultNorm);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [suggesting, setSuggesting] = useState(false);

  const inspected = files.filter((f) => f.status === 'inspected');
  const sourceFile = files.find((f) => f.id === sourceFileId);
  const targetFile = files.find((f) => f.id === targetFileId);

  const load = async () => {
    const [fs, ms] = await Promise.all([listFiles(projectId), listMappings(projectId)]);
    setFiles(fs);
    setMappings(ms);
    const src = fs.find((f) => f.role === 'source' && f.status === 'inspected');
    const tgt = fs.find((f) => f.role === 'target' && f.status === 'inspected');
    if (src) setSourceFileId(src.id);
    if (tgt) setTargetFileId(tgt.id);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const suggest = async () => {
    if (!sourceFileId || !targetFileId) return;
    setSuggesting(true);
    setError(null);
    try {
      const res = await getMappingSuggestions(projectId, sourceFileId, targetFileId);
      const suggested = res.suggestions.map((s) => ({
        ...emptyField(),
        source_columns: [s.source_column],
        target_column: s.target_column,
        data_type: guessType(res.source_columns[s.source_column]),
      }));
      setFields(suggested);
      if (!mappingName) {
        setMappingName(`${sourceFile?.original_filename.replace('.csv', '')} → ${targetFile?.original_filename.replace('.csv', '')}`);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSuggesting(false);
    }
  };

  const guessType = (duckdbType?: string): 'string' | 'numeric' | 'date' => {
    if (!duckdbType) return 'string';
    const t = duckdbType.toUpperCase();
    if (t.includes('INT') || t.includes('DOUBLE') || t.includes('DECIMAL') || t.includes('FLOAT')) return 'numeric';
    if (t.includes('DATE') || t.includes('TIME')) return 'date';
    return 'string';
  };

  // Note: files are always stored all-VARCHAR internally (see backend
  // file_inspector.py) to avoid silent row loss during CSV ingestion, so
  // `columns_json` here holds the *detected display type* from a typed
  // sample scan — useful to catch source/target type mismatches at mapping
  // time, but not the literal storage type.
  const typeFamilyLabel = (duckdbType?: string) => {
    if (!duckdbType) return { family: 'unknown', label: '—' };
    return { family: guessType(duckdbType), label: duckdbType };
  };

  const addField = () => setFields((f) => [...f, emptyField()]);
  const removeField = (i: number) => setFields((f) => f.filter((_, idx) => idx !== i));
  const updateField = (i: number, patch: Partial<FieldMapping>) =>
    setFields((f) => f.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));

  const save = async () => {
    setError(null);
    if (!sourceFileId || !targetFileId) {
      setError('Select both a source and target file.');
      return;
    }
    if (!mappingName.trim()) {
      setError('Give this mapping a name.');
      return;
    }
    const valid = fields.filter((f) => f.source_columns.length > 0 && f.target_column);
    if (!valid.some((f) => f.is_matching_key)) {
      setError('Mark at least one mapped field as a matching key.');
      return;
    }
    setSaving(true);
    try {
      const mc = await createMapping(projectId, {
        name: mappingName.trim(),
        source_file_id: sourceFileId,
        target_file_id: targetFileId,
        column_mappings: valid,
        normalization: norm,
      });
      setMappings((m) => [mc, ...m]);
      onCreated?.(mc);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: string) => {
    if (!confirm('Delete this mapping configuration?')) return;
    await deleteMapping(projectId, id);
    setMappings((m) => m.filter((x) => x.id !== id));
  };

  if (files.length === 0) {
    return (
      <Card>
        <EmptyState title="Upload files first" subtitle="You need at least one source and one target file before configuring a mapping." />
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="p-5">
        <h2 className="font-medium text-slate-800 mb-3">1. Choose source &amp; target files</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="text-sm text-slate-600 block mb-1">Source file</label>
            <select
              value={sourceFileId}
              onChange={(e) => setSourceFileId(e.target.value)}
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
            >
              <option value="">Select source file...</option>
              {inspected.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.original_filename} ({f.row_count?.toLocaleString()} rows)
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-sm text-slate-600 block mb-1">Target file</label>
            <select
              value={targetFileId}
              onChange={(e) => setTargetFileId(e.target.value)}
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
            >
              <option value="">Select target file...</option>
              {inspected.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.original_filename} ({f.row_count?.toLocaleString()} rows)
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-4">
          <Button variant="secondary" onClick={suggest} disabled={!sourceFileId || !targetFileId || suggesting}>
            {suggesting ? <Spinner /> : <Sparkles className="h-3.5 w-3.5" />} Suggest Mappings
          </Button>
          <span className="text-xs text-slate-400 ml-2">Suggestions are pre-filled below — review and confirm before saving.</span>
        </div>
      </Card>

      {(sourceFileId && targetFileId) && (
        <Card className="p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-medium text-slate-800">2. Configure column mapping</h2>
            <Button variant="secondary" onClick={addField}>
              <Plus className="h-3.5 w-3.5" /> Add Field
            </Button>
          </div>

          <div className="mb-4">
            <label className="text-sm text-slate-600 block mb-1">Mapping name</label>
            <input
              value={mappingName}
              onChange={(e) => setMappingName(e.target.value)}
              placeholder="e.g. Customer Migration v1"
              className="w-full md:w-96 border border-slate-300 rounded-md px-3 py-2 text-sm"
            />
          </div>

          {fields.length === 0 && (
            <EmptyState title="No fields mapped yet" subtitle='Click "Suggest Mappings" or "Add Field" to get started.' />
          )}

          <div className="space-y-2">
            {fields.map((f, i) => {
              const srcCol = f.source_columns[0] || '';
              const srcType = sourceFile?.columns_json[srcCol];
              const tgtType = targetFile?.columns_json[f.target_column];
              const srcFamily = typeFamilyLabel(srcType);
              const tgtFamily = typeFamilyLabel(tgtType);
              const familyMismatch =
                srcCol && f.target_column && srcFamily.family !== 'unknown' && tgtFamily.family !== 'unknown' &&
                srcFamily.family !== tgtFamily.family;
              return (
                <div key={i} className="border border-slate-200 rounded-md p-2 bg-slate-50/50">
                  <div className="grid grid-cols-12 gap-2 items-center">
                    <select
                      className="col-span-3 border border-slate-300 rounded px-2 py-1.5 text-sm bg-white"
                      value={srcCol}
                      onChange={(e) => updateField(i, { source_columns: e.target.value ? [e.target.value] : [] })}
                    >
                      <option value="">Source column...</option>
                      {sourceFile && Object.keys(sourceFile.columns_json).map((c) => (
                        <option key={c} value={c}>{c} ({sourceFile.columns_json[c]})</option>
                      ))}
                    </select>
                    <div className="col-span-1 flex justify-center text-slate-300">
                      <ArrowRight className="h-4 w-4" />
                    </div>
                    <select
                      className="col-span-3 border border-slate-300 rounded px-2 py-1.5 text-sm bg-white"
                      value={f.target_column}
                      onChange={(e) => updateField(i, { target_column: e.target.value })}
                    >
                      <option value="">Target column...</option>
                      {targetFile && Object.keys(targetFile.columns_json).map((c) => (
                        <option key={c} value={c}>{c} ({targetFile.columns_json[c]})</option>
                      ))}
                    </select>
                    <select
                      className="col-span-2 border border-slate-300 rounded px-2 py-1.5 text-sm bg-white"
                      value={f.data_type}
                      onChange={(e) => updateField(i, { data_type: e.target.value as FieldMapping['data_type'] })}
                    >
                      <option value="string">String</option>
                      <option value="numeric">Numeric</option>
                      <option value="date">Date</option>
                    </select>
                    <label className="col-span-1 flex items-center gap-1 text-xs text-slate-600" title="Matching key">
                      <input
                        type="checkbox"
                        checked={f.is_matching_key}
                        onChange={(e) => updateField(i, { is_matching_key: e.target.checked, compare_in_validation: e.target.checked ? false : f.compare_in_validation })}
                      />
                      <KeyRound className="h-3.5 w-3.5" />
                    </label>
                    <label className="col-span-1 flex items-center gap-1 text-xs text-slate-600">
                      <input
                        type="checkbox"
                        checked={f.required}
                        onChange={(e) => updateField(i, { required: e.target.checked })}
                      />
                      Req.
                    </label>
                    <button onClick={() => removeField(i)} className="col-span-1 text-slate-400 hover:text-red-600 flex justify-end">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  {(srcCol || f.target_column) && (
                    <div className={`flex items-center gap-3 text-xs mt-1.5 pl-1 ${familyMismatch ? 'text-amber-700' : 'text-slate-400'}`}>
                      <span>Source type: <span className="font-medium">{srcFamily.label}</span></span>
                      <span>Target type: <span className="font-medium">{tgtFamily.label}</span></span>
                      {familyMismatch && (
                        <span className="flex items-center gap-1">
                          <AlertTriangle className="h-3 w-3" /> Different data types — check the Data Type dropdown and normalization before relying on this comparison.
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div className="text-xs text-slate-400 mt-2">
            <KeyRound className="h-3 w-3 inline mr-1" />= this field is (part of) the matching key used to find records across source and
            target. Mark multiple fields to build a composite key.
          </div>

          <h3 className="font-medium text-slate-800 mt-6 mb-2">3. Normalization rules</h3>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={norm.trim} onChange={(e) => setNorm({ ...norm, trim: e.target.checked })} /> Trim whitespace
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={norm.case_insensitive} onChange={(e) => setNorm({ ...norm, case_insensitive: e.target.checked })} /> Case insensitive
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={norm.numeric_normalize} onChange={(e) => setNorm({ ...norm, numeric_normalize: e.target.checked })} /> Numeric normalization
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={norm.date_normalize} onChange={(e) => setNorm({ ...norm, date_normalize: e.target.checked })} /> Date normalization
            </label>
          </div>

          {error && <div className="text-red-700 bg-red-50 border border-red-200 rounded-md p-3 text-sm mt-4">{error}</div>}

          <div className="mt-5">
            <Button onClick={save} disabled={saving}>
              {saving ? <Spinner /> : <Save className="h-3.5 w-3.5" />} Save Mapping
            </Button>
          </div>
        </Card>
      )}

      {mappings.length > 0 && (
        <Card className="p-5">
          <h2 className="font-medium text-slate-800 mb-3">Saved mappings</h2>
          <div className="space-y-2">
            {mappings.map((m) => (
              <div key={m.id} className="flex items-center justify-between border border-slate-200 rounded-md px-3 py-2">
                <div>
                  <div className="text-sm font-medium text-slate-800">{m.name}</div>
                  <div className="text-xs text-slate-500">{m.column_mappings_json.length} fields mapped</div>
                </div>
                <button onClick={() => remove(m.id)} className="text-slate-400 hover:text-red-600">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
