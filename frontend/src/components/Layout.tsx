import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Database, LayoutDashboard } from 'lucide-react';

export function Layout({ children }: { children: ReactNode }) {
  const loc = useLocation();
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-3">
          <Link to="/" className="flex items-center gap-2 font-semibold text-slate-800">
            <div className="h-7 w-7 rounded bg-(--color-brand-600) text-white flex items-center justify-center">
              <Database className="h-4 w-4" />
            </div>
            Migration Validation Tool
          </Link>
          <nav className="ml-8 flex items-center gap-4 text-sm">
            <Link
              to="/"
              className={`flex items-center gap-1.5 px-2 py-1 rounded ${loc.pathname === '/' ? 'text-(--color-brand-600) font-medium' : 'text-slate-500 hover:text-slate-800'}`}
            >
              <LayoutDashboard className="h-3.5 w-3.5" /> Projects
            </Link>
          </nav>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-6 py-6">{children}</main>
    </div>
  );
}
