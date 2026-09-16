import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Upload, GitMerge, PlayCircle, History as HistoryIcon } from 'lucide-react';
import { getProject } from '../api/client';
import type { Project } from '../types';
import { FilesTab } from './project/FilesTab';
import { MappingTab } from './project/MappingTab';
import { ValidationTab } from './project/ValidationTab';
import { HistoryTab } from './project/HistoryTab';
import { Spinner } from '../components/ui';

const STEPS = [
  { key: 'files', label: '1. Files', icon: Upload },
  { key: 'mapping', label: '2. Mapping', icon: GitMerge },
  { key: 'validation', label: '3. Validation & Results', icon: PlayCircle },
  { key: 'history', label: '4. History', icon: HistoryIcon },
] as const;

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [step, setStep] = useState<(typeof STEPS)[number]['key']>('files');

  useEffect(() => {
    if (projectId) getProject(projectId).then(setProject);
  }, [projectId]);

  if (!projectId) return null;
  if (!project) {
    return (
      <div className="py-20 text-center">
        <Spinner className="mx-auto text-(--color-brand-600)" />
      </div>
    );
  }

  return (
    <div>
      <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 mb-4">
        <ArrowLeft className="h-3.5 w-3.5" /> All Projects
      </Link>
      <h1 className="text-xl font-semibold text-slate-900 mb-1">{project.name}</h1>
      {project.description && <p className="text-sm text-slate-500 mb-5">{project.description}</p>}

      <div className="flex gap-1 border-b border-slate-200 mb-6 overflow-x-auto">
        {STEPS.map((s) => (
          <button
            key={s.key}
            onClick={() => setStep(s.key)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm whitespace-nowrap border-b-2 -mb-px ${
              step === s.key ? 'border-(--color-brand-600) text-(--color-brand-600) font-medium' : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            <s.icon className="h-4 w-4" /> {s.label}
          </button>
        ))}
      </div>

      {step === 'files' && <FilesTab projectId={projectId} />}
      {step === 'mapping' && <MappingTab projectId={projectId} onCreated={() => setStep('validation')} />}
      {step === 'validation' && <ValidationTab projectId={projectId} />}
      {step === 'history' && <HistoryTab projectId={projectId} />}
    </div>
  );
}
