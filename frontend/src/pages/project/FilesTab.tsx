import { useEffect, useRef, useState } from 'react';
import { Upload, FileText, Eye, Trash2, AlertTriangle } from 'lucide-react';
import { listFiles, uploadFile, setFileRole, previewFile, deleteFile } from '../../api/client';
import type { UploadedFile } from '../../types';
import { Card, StatusBadge, EmptyState, Spinner } from '../../components/ui';

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function FilesTab({ projectId, onChanged }: { projectId: string; onChanged?: () => void }) {
  const [files, setFiles] = useState<UploadedFile[] | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [previewFor, setPreviewFor] = useState<UploadedFile | null>(null);
  const [previewData, setPreviewData] = useState<{ columns: Record<string, string>; rows: Record<string, unknown>[]; row_count: number; warnings: string[] } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = () => listFiles(projectId).then(setFiles);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const doUpload = async (fileList: FileList | null) => {
    if (!fileList) return;
    for (const f of Array.from(fileList)) {
      if (!f.name.toLowerCase().endsWith('.csv')) continue;
      setUploading(f.name);
      try {
        await uploadFile(projectId, f);
      } catch {
        // errors surface via file.status === 'error' after reload
      }
    }
    setUploading(null);
    load();
    onChanged?.();
  };

  const changeRole = async (fileId: string, role: string) => {
    await setFileRole(projectId, fileId, role);
    load();
    onChanged?.();
  };

  const remove = async (fileId: string) => {
    if (!confirm('Remove this file from the project?')) return;
    await deleteFile(projectId, fileId);
    load();
    onChanged?.();
  };

  const openPreview = async (f: UploadedFile) => {
    setPreviewFor(f);
    setPreviewData(null);
    if (f.status === 'inspected') {
      const data = await previewFile(projectId, f.id, 25);
      setPreviewData(data);
    }
  };

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          doUpload(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors mb-6 ${
          dragOver ? 'border-(--color-brand-600) bg-blue-50' : 'border-slate-300 hover:border-slate-400 bg-white'
        }`}
      >
        <Upload className="h-7 w-7 mx-auto text-slate-400 mb-2" />
        <div className="text-sm text-slate-600">
          <span className="text-(--color-brand-600) font-medium">Click to upload</span> or drag and drop CSV files
        </div>
        <div className="text-xs text-slate-400 mt-1">Multiple files supported. Large files are streamed and processed server-side.</div>
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          multiple
          className="hidden"
          onChange={(e) => doUpload(e.target.files)}
        />
        {uploading && (
          <div className="mt-3 text-sm text-(--color-brand-600) flex items-center justify-center gap-2">
            <Spinner /> Uploading {uploading}...
          </div>
        )}
      </div>

      {!files && (
        <div className="py-10 text-center">
          <Spinner className="mx-auto text-(--color-brand-600)" />
        </div>
      )}

      {files && files.length === 0 && (
        <Card>
          <EmptyState title="No files uploaded yet" subtitle="Upload source and target CSV files to begin." />
        </Card>
      )}

      {files && files.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {files.map((f) => (
            <Card key={f.id} className="p-4">
              <div className="flex items-start justify-between">
                <div className="flex gap-3 min-w-0">
                  <FileText className="h-5 w-5 text-slate-400 shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <div className="font-medium text-slate-800 truncate" title={f.original_filename}>
                      {f.original_filename}
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">{formatBytes(f.file_size_bytes)}</div>
                  </div>
                </div>
                <StatusBadge status={f.status} />
              </div>

              {f.status === 'error' && (
                <div className="mt-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded p-2 flex gap-1.5">
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" /> {f.error_message}
                </div>
              )}

              {f.status === 'inspected' && (
                <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-slate-600">
                  <div>
                    <div className="text-slate-400">Rows</div>
                    <div className="font-medium">{f.row_count?.toLocaleString()}</div>
                  </div>
                  <div>
                    <div className="text-slate-400">Columns</div>
                    <div className="font-medium">{f.column_count}</div>
                  </div>
                  <div>
                    <div className="text-slate-400">Encoding</div>
                    <div className="font-medium">{f.encoding}{f.has_bom ? ' (BOM)' : ''}</div>
                  </div>
                </div>
              )}

              {f.parse_warnings_json?.length > 0 && (
                <div className="mt-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
                  {f.parse_warnings_json.join(' ')}
                </div>
              )}

              <div className="flex items-center justify-between mt-3">
                <select
                  value={f.role}
                  onChange={(e) => changeRole(f.id, e.target.value)}
                  className="text-xs border border-slate-300 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-(--color-brand-600)"
                >
                  <option value="unassigned">Unassigned</option>
                  <option value="source">Source</option>
                  <option value="target">Target</option>
                </select>
                <div className="flex gap-1">
                  <button
                    onClick={() => openPreview(f)}
                    disabled={f.status !== 'inspected'}
                    className="text-slate-400 hover:text-(--color-brand-600) disabled:opacity-30 p-1"
                    title="Preview"
                  >
                    <Eye className="h-4 w-4" />
                  </button>
                  <button onClick={() => remove(f.id)} className="text-slate-400 hover:text-red-600 p-1" title="Delete">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {previewFor && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-6" onClick={() => setPreviewFor(null)}>
          <div className="bg-white rounded-lg max-w-5xl w-full max-h-[80vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
              <div>
                <div className="font-medium text-slate-800">{previewFor.original_filename}</div>
                <div className="text-xs text-slate-500">
                  {previewFor.row_count?.toLocaleString()} rows &middot; {previewFor.column_count} columns &middot; delimiter "{previewFor.delimiter}"
                </div>
              </div>
              <button onClick={() => setPreviewFor(null)} className="text-slate-400 hover:text-slate-700">
                ✕
              </button>
            </div>
            <div className="overflow-auto p-0">
              {!previewData ? (
                <div className="p-10 text-center">
                  <Spinner className="mx-auto text-(--color-brand-600)" />
                </div>
              ) : (
                <table className="min-w-full text-xs">
                  <thead className="bg-slate-50 sticky top-0">
                    <tr>
                      {Object.entries(previewData.columns).map(([name, type]) => (
                        <th key={name} className="text-left px-3 py-2 font-medium text-slate-600 whitespace-nowrap border-b border-slate-200">
                          {name}
                          <div className="text-slate-400 font-normal">{type}</div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {previewData.rows.map((row, i) => (
                      <tr key={i}>
                        {Object.keys(previewData.columns).map((c) => (
                          <td key={c} className="px-3 py-1.5 whitespace-nowrap text-slate-700">
                            {row[c] === null ? <span className="text-slate-300 italic">null</span> : String(row[c])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <div className="text-xs text-slate-400 px-5 py-2 border-t border-slate-100">Showing first 25 rows only.</div>
          </div>
        </div>
      )}
    </div>
  );
}
