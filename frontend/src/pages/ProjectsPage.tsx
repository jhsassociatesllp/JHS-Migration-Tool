import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, FolderKanban, X } from 'lucide-react';
import { listProjects, createProject, deleteProject } from '../api/client';
import type { Project } from '../types';
import { Card, Button, EmptyState, Spinner } from '../components/ui';

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);
  const nav = useNavigate();

  const load = () => listProjects().then(setProjects).catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  const submit = async () => {
    if (!name.trim()) return;
    try {
      const p = await createProject(name.trim(), description.trim() || undefined);
      setShowCreate(false);
      setName('');
      setDescription('');
      nav(`/projects/${p.id}`);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const remove = async (id: string) => {
    if (!confirm('Delete this project and all its files, mappings, and validation results? This cannot be undone.')) return;
    await deleteProject(id);
    load();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Migration Projects</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Create a project per migration to keep files, mappings, and validation history organized.
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4" /> New Project
        </Button>
      </div>

      {error && <div className="text-red-700 bg-red-50 border border-red-200 rounded-md p-3 text-sm mb-4">{error}</div>}

      {showCreate && (
        <Card className="p-5 mb-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-medium text-slate-800">Create Migration Project</h2>
            <button onClick={() => setShowCreate(false)} className="text-slate-400 hover:text-slate-600">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="space-y-3">
            <div>
              <label className="text-sm text-slate-600 block mb-1">Project Name</label>
              <input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Customer Database Migration - September 2026"
                className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-(--color-brand-600)"
              />
            </div>
            <div>
              <label className="text-sm text-slate-600 block mb-1">Description (optional)</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-(--color-brand-600)"
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={submit}>Create Project</Button>
              <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancel</Button>
            </div>
          </div>
        </Card>
      )}

      {!projects && (
        <div className="py-16 text-center">
          <Spinner className="mx-auto text-(--color-brand-600)" />
        </div>
      )}

      {projects && projects.length === 0 && !showCreate && (
        <Card>
          <EmptyState title="No migration projects yet" subtitle="Create a project to start uploading and validating CSV files." />
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {projects?.map((p) => (
          <Card key={p.id} className="p-4 hover:shadow-md transition-shadow cursor-pointer group" >
            <div onClick={() => nav(`/projects/${p.id}`)}>
              <div className="flex items-start justify-between">
                <div className="h-9 w-9 rounded-lg bg-blue-50 text-(--color-brand-600) flex items-center justify-center mb-3">
                  <FolderKanban className="h-4.5 w-4.5" />
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    remove(p.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 text-xs"
                >
                  Delete
                </button>
              </div>
              <div className="font-medium text-slate-900">{p.name}</div>
              {p.description && <div className="text-sm text-slate-500 mt-1 line-clamp-2">{p.description}</div>}
              <div className="flex gap-4 mt-3 text-xs text-slate-500">
                <span>{p.file_count ?? 0} files</span>
                <span>{p.run_count ?? 0} validation runs</span>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
