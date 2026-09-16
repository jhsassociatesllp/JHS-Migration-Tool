import type { ReactNode } from 'react';

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: 'bg-emerald-100 text-emerald-800 border-emerald-300',
    passed: 'bg-emerald-100 text-emerald-800 border-emerald-300',
    running: 'bg-blue-100 text-blue-800 border-blue-300',
    queued: 'bg-slate-100 text-slate-700 border-slate-300',
    failed: 'bg-red-100 text-red-800 border-red-300',
    warning: 'bg-amber-100 text-amber-800 border-amber-300',
    error: 'bg-red-100 text-red-800 border-red-300',
    inspected: 'bg-emerald-100 text-emerald-800 border-emerald-300',
    uploaded: 'bg-slate-100 text-slate-700 border-slate-300',
  };
  const cls = map[status] ?? 'bg-slate-100 text-slate-700 border-slate-300';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${cls}`}>
      {status}
    </span>
  );
}

export function ProgressBar({ percent }: { percent: number }) {
  return (
    <div className="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden">
      <div
        className="bg-(--color-brand-600) h-2.5 rounded-full transition-all duration-300"
        style={{ width: `${Math.max(2, Math.min(100, percent))}%` }}
      />
    </div>
  );
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`bg-white rounded-lg border border-slate-200 shadow-sm ${className}`}>{children}</div>;
}

export function StatCard({ label, value, tone = 'default' }: { label: string; value: string | number; tone?: 'default' | 'good' | 'bad' | 'warn' }) {
  const toneClass: Record<string, string> = {
    default: 'text-slate-900',
    good: 'text-emerald-700',
    bad: 'text-red-700',
    warn: 'text-amber-700',
  };
  return (
    <Card className="p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500 font-medium">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${toneClass[tone]}`}>{value.toLocaleString ? value.toLocaleString() : value}</div>
    </Card>
  );
}

export function Button({
  children, onClick, variant = 'primary', disabled, className = '', type = 'button',
}: {
  children: ReactNode; onClick?: () => void; variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  disabled?: boolean; className?: string; type?: 'button' | 'submit';
}) {
  const base = 'inline-flex items-center gap-1.5 px-3.5 py-2 rounded-md text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
  const variants: Record<string, string> = {
    primary: 'bg-(--color-brand-600) text-white hover:bg-(--color-brand-700)',
    secondary: 'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50',
    danger: 'bg-red-600 text-white hover:bg-red-700',
    ghost: 'text-slate-600 hover:bg-slate-100',
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${base} ${variants[variant]} ${className}`}>
      {children}
    </button>
  );
}

export function EmptyState({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="text-center py-14 text-slate-500">
      <div className="font-medium text-slate-700">{title}</div>
      {subtitle && <div className="text-sm mt-1">{subtitle}</div>}
    </div>
  );
}

export function Spinner({ className = '' }: { className?: string }) {
  return (
    <svg className={`animate-spin h-4 w-4 ${className}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}
