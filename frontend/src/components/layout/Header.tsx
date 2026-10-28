import React from 'react';
import { Badge } from '@/components/ui/Badge';
import { ShieldCheck, FileSpreadsheet, Server, Database } from 'lucide-react';

interface HeaderProps {
  documentCount?: number;
}

export const Header: React.FC<HeaderProps> = ({ documentCount = 0 }) => {
  return (
    <header className="h-14 bg-[#111116] border-b border-gray-800 px-4 lg:px-6 flex items-center justify-between z-20 shrink-0">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-cyan-400 flex items-center justify-center shadow-lg shadow-indigo-600/20">
          <FileSpreadsheet size={18} className="text-white" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-sm font-bold tracking-tight text-white">
              AI-Powered Document Intelligence System
            </h1>
            <span className="text-[10px] bg-indigo-500/20 text-indigo-400 px-1.5 py-0.5 rounded font-mono border border-indigo-500/30">
              v2.0 PROD
            </span>
          </div>
          <p className="text-[10px] text-gray-400">
            Multi-Format OCR (PDF, TIFF, Images) • Spreadsheet Ingestion (XLSX, CSV) • Automated Math Auditing
          </p>
        </div>

        <div className="h-4 w-px bg-gray-800 mx-2 hidden md:block" />

        <div className="items-center gap-2 hidden md:flex text-[11px]">
          <Badge variant="success" dot>
            <span className="flex items-center gap-1">
              <Server size={11} /> FastAPI Gateway :8000
            </span>
          </Badge>
          <Badge variant="primary" dot>
            <span className="flex items-center gap-1">
              <Database size={11} /> PostgreSQL + pgvector
            </span>
          </Badge>
        </div>
      </div>

      <div className="flex items-center gap-4 text-xs font-mono text-gray-400">
        <div className="items-center gap-1.5 hidden sm:flex">
          <span className="text-gray-500">Active Queue:</span>
          <strong className="text-indigo-400 bg-indigo-950/60 px-2 py-0.5 rounded border border-indigo-800/40">
            {documentCount} files
          </strong>
        </div>
        <div className="flex items-center gap-1.5">
          <ShieldCheck size={14} className="text-emerald-400" />
          <span className="text-gray-300">Zero Hallucination Guardrail: <strong className="text-emerald-400">ACTIVE</strong></span>
        </div>
      </div>
    </header>
  );
};
