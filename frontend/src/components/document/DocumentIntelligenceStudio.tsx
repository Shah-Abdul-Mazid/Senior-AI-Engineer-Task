import { useState, useEffect, useRef, useCallback } from 'react';
import {
  UploadCloud,
  FileText,
  FileSpreadsheet,
  Search,
  BarChart3,
  GitCompare,
  RefreshCw,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Edit3,
  Save,
  RotateCw,
  Eye,
  ZoomIn,
  ZoomOut,
  Layers,
  Sparkles,
  ShieldCheck,
  ShieldAlert,
  Check,
  X,
  ChevronRight,
  TrendingUp,
  Activity,
  Package,
} from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ApiClient } from '@/services/client';

// ─── Types ──────────────────────────────────────────────────────────────────

interface LineItem {
  id?: string;
  description: string;
  quantity: number | null;
  unit_price: number | null;
  amount: number | null;
}

interface InvoiceData {
  id?: string;
  document_id?: string;
  invoice_number: string | null;
  purchase_order_number?: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  customer_name: string | null;
  currency: string | null;
  subtotal: number | null;
  tax: number | null;
  total: number | null;
  confidence_score: number;
  extraction_notes?: string | null;
  is_corrected?: boolean;
  line_items: LineItem[];
}

interface ValidationError {
  error_type: string;
  severity: 'error' | 'warning' | 'info';
  field_name?: string | null;
  message: string;
  expected_value?: string | null;
  actual_value?: string | null;
}

interface DocumentItem {
  document_id: string;
  filename: string;
  file_type: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'requires_review';
  invoice_number?: string | null;
  supplier_name?: string | null;
  total?: number | null;
  currency?: string | null;
  has_errors: boolean;
  created_at: string;
}

interface DatasetStats {
  dataset_directory: string;
  total_documents: number;
  ocr_annotations_count: number;
  ground_truth_count: number;
  sample_files: string[];
}

interface EvalReport {
  evaluation_timestamp: string;
  dataset: { total_available_in_dataset: number; evaluated_sample_size: number };
  performance_metrics: {
    document_success_rate_percent: number;
    document_failure_rate_percent: number;
    manual_review_rate_percent: number;
    average_processing_time_ms: number;
    min_processing_time_ms: number;
    max_processing_time_ms: number;
  };
  field_extraction_accuracy: {
    overall_accuracy_percent: number;
    invoice_number_accuracy_percent: number;
    supplier_name_accuracy_percent: number;
    total_amount_accuracy_percent: number;
    invoice_date_accuracy_percent: number;
  };
  sample_results: any[];
}

interface DocumentStudioProps {
  onQueueCountChange?: (count: number) => void;
}

// ─── Helper ──────────────────────────────────────────────────────────────────

const BLANK_INVOICE: InvoiceData = {
  invoice_number: null, purchase_order_number: null, invoice_date: null, supplier_name: null,
  customer_name: null, currency: 'USD', subtotal: null, tax: null,
  total: null, confidence_score: 0, line_items: [],
};

const SAMPLE_FILES = [
  { name: 'invoice.xlsx',       icon: 'xlsx', label: 'XLSX – Multi-item Spreadsheet' },
  { name: 'batch1-0494.jpg',    icon: 'jpg',  label: 'JPG – Batch Invoice Image' },
  { name: 'batch1-0489.jpg',    icon: 'jpg',  label: 'JPG – Clean Invoice Photo' },
  { name: '0000223278.tif',     icon: 'tif',  label: 'TIFF – Scanned Legacy Invoice' },
  { name: '0060094822.tif',     icon: 'tif',  label: 'TIFF – Rowland Co. Scanned' },
  { name: 'tob02910.64.tif',    icon: 'tif',  label: 'TIFF – Recapitulation Sheet' },
];


function StatusIcon({ status }: { status: string }) {
  if (status === 'completed')       return <CheckCircle2 size={12} className="text-emerald-400 shrink-0" />;
  if (status === 'requires_review') return <AlertTriangle size={12} className="text-amber-400 shrink-0" />;
  if (status === 'processing')      return <RefreshCw size={12} className="text-indigo-400 animate-spin shrink-0" />;
  if (status === 'failed')          return <XCircle size={12} className="text-rose-400 shrink-0" />;
  return <Clock size={12} className="text-gray-400 shrink-0" />;
}

function FileIcon({ type }: { type: string }) {
  if (type === 'xlsx' || type === 'xls' || type === 'csv')
    return <FileSpreadsheet size={13} className="text-emerald-400 shrink-0" />;
  if (type === 'tif' || type === 'tiff')
    return <Layers size={13} className="text-cyan-400 shrink-0" />;
  return <FileText size={13} className="text-indigo-400 shrink-0" />;
}

// ─── Nav Tab ─────────────────────────────────────────────────────────────────

type NavView = 'process' | 'search' | 'verify' | 'evaluate';

const NAV_ITEMS: { id: NavView; label: string; icon: React.ReactNode; desc: string }[] = [
  { id: 'process',  label: 'Process',   icon: <Package size={16} />,     desc: 'Upload, Queue & Extract' },
  { id: 'search',   label: 'Search',    icon: <Search size={16} />,      desc: 'Keyword & Semantic Query' },
  { id: 'verify',   label: 'Verify',    icon: <GitCompare size={16} />,  desc: 'PDF vs Excel Cross-Check' },
  { id: 'evaluate', label: 'Evaluate',  icon: <BarChart3 size={16} />,   desc: 'Task 7 Benchmark Report' },
];

// ═════════════════════════════════════════════════════════════════════════════
// Main Studio Component
// ═════════════════════════════════════════════════════════════════════════════

export default function DocumentIntelligenceStudio({ onQueueCountChange }: DocumentStudioProps = {}) {
  const [activeView, setActiveView] = useState<NavView>('process');
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [currentDocName, setCurrentDocName] = useState<string>('No document selected');
  const [currentDocStatus, setCurrentDocStatus] = useState<string>('pending');
  const [currentRawText, setCurrentRawText] = useState<string>('');
  const [viewMode, setViewMode] = useState<'visual' | 'text'>('visual');
  const [zoom, setZoom] = useState(100);
  const [currentInvoice, setCurrentInvoice] = useState<InvoiceData>(BLANK_INVOICE);
  const [currentValidationErrors, setCurrentValidationErrors] = useState<ValidationError[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const [saveNotice, setSaveNotice] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [queueFilter, setQueueFilter] = useState<'all' | 'completed' | 'requires_review' | 'failed'>('all');
  const [queueSearch, setQueueSearch] = useState('');
  const [datasetStats, setDatasetStats] = useState<DatasetStats | null>(null);
  // Search view
  const [searchQuery, setSearchQuery] = useState('');
  const [searchMode, setSearchMode] = useState<'keyword' | 'semantic' | 'hybrid'>('hybrid');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  // Verify view
  const [verifyDocA, setVerifyDocA] = useState<string>('');
  const [verifyDocB, setVerifyDocB] = useState<string>('');
  const [verifyResult, setVerifyResult] = useState<any>(null);
  const [isVerifying, setIsVerifying] = useState(false);
  // Evaluate view
  const [evalReport, setEvalReport] = useState<EvalReport | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [evalSampleSize, setEvalSampleSize] = useState(20);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── API helpers ────────────────────────────────────────────────────────────

  const fetchDocuments = useCallback(async () => {
    try {
      const data = await ApiClient.get<DocumentItem[]>('/api/v1/documents/');
      if (Array.isArray(data)) {
        setDocuments(data);
        onQueueCountChange?.(data.length);
        return data;
      }
    } catch { /* graceful */ }
    return [];
  }, [onQueueCountChange]);

  const loadDocResult = useCallback(async (docId: string, docName?: string) => {
    setSelectedDocId(docId);
    if (docName) setCurrentDocName(docName);
    try {
      const result: any = await ApiClient.get(`/api/v1/documents/${docId}/result`);
      setCurrentDocName(result.filename || docName || 'Document');
      setCurrentDocStatus(result.status || 'completed');
      if (result.raw_text) setCurrentRawText(result.raw_text);
      if (result.invoice) {
        setCurrentInvoice({
          id: result.invoice.id,
          document_id: docId,
          invoice_number: result.invoice.invoice_number,
          purchase_order_number: result.invoice.purchase_order_number,
          invoice_date: result.invoice.invoice_date,
          supplier_name: result.invoice.supplier_name,
          customer_name: result.invoice.customer_name,
          currency: result.invoice.currency || 'USD',
          subtotal: result.invoice.subtotal,
          tax: result.invoice.tax ?? 0,
          total: result.invoice.total,
          confidence_score: result.invoice.confidence_score ?? 0.85,
          is_corrected: result.invoice.is_corrected,
          extraction_notes: result.invoice.extraction_notes,
          line_items: result.invoice.line_items || [],
        });
      } else {
        setCurrentInvoice(BLANK_INVOICE);
      }
      setCurrentValidationErrors(result.validation_errors || []);
    } catch (e) {
      console.warn('Result load error:', e);
    }
  }, []);

  const fetchDatasetStats = async () => {
    try {
      const s = await ApiClient.get<DatasetStats>('/api/v1/documents/dataset/stats');
      setDatasetStats(s as unknown as DatasetStats);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    (async () => {
      const docs = await fetchDocuments();
      if (docs.length > 0) loadDocResult(docs[0].document_id, docs[0].filename);
      fetchDatasetStats();
    })();
  }, [fetchDocuments, loadDocResult]);

  // Polling while docs are processing
  useEffect(() => {
    const hasActive = documents.some(d => d.status === 'pending' || d.status === 'processing');
    if (!hasActive) return;
    const t = setInterval(async () => {
      const docs = await fetchDocuments();
      if (selectedDocId) {
        const cur = docs.find(d => d.document_id === selectedDocId);
        if (cur && cur.status !== currentDocStatus) loadDocResult(selectedDocId, cur.filename);
      }
    }, 2500);
    return () => clearInterval(t);
  }, [documents, selectedDocId, currentDocStatus, fetchDocuments, loadDocResult]);

  // ── Upload ─────────────────────────────────────────────────────────────────

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setIsUploading(true);
    const fd = new FormData();
    for (let i = 0; i < files.length; i++) fd.append('files', files[i]);
    try {
      const resp: any = await ApiClient.post('/api/v1/documents/upload', fd);
      const docs = await fetchDocuments();
      const first = resp.uploaded?.[0];
      if (first) {
        loadDocResult(first.document_id, first.filename);
      } else if (docs.length > 0) {
        loadDocResult(docs[0].document_id, docs[0].filename);
      }
      setActiveView('process');
    } catch (err: any) {
      alert(`Upload failed: ${err.message}`);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleLoadSample = async (name: string) => {
    try {
      const res: any = await ApiClient.post(`/api/v1/documents/load-sample?filename=${encodeURIComponent(name)}`);
      const docs = await fetchDocuments();
      if (res?.document_id) loadDocResult(res.document_id, name);
      else if (docs.length > 0) loadDocResult(docs[0].document_id, docs[0].filename);
      setActiveView('process');
    } catch (err: any) {
      alert(`Could not load sample: ${err.message}`);
    }
  };

  const handleRetry = async () => {
    if (!selectedDocId) return;
    setIsRetrying(true);
    try {
      await ApiClient.post(`/api/v1/documents/${selectedDocId}/retry`);
      await fetchDocuments();
      await loadDocResult(selectedDocId, currentDocName);
    } catch (err: any) {
      alert(`Retry failed: ${err.message}`);
    } finally {
      setIsRetrying(false);
    }
  };

  const handleDeleteDoc = async (docId: string, name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Delete "${name}"?`)) return;
    try {
      await ApiClient.delete(`/api/v1/documents/${docId}`);
      const docs = await fetchDocuments();
      if (selectedDocId === docId) {
        if (docs.length > 0) loadDocResult(docs[0].document_id, docs[0].filename);
        else { setSelectedDocId(null); setCurrentInvoice(BLANK_INVOICE); setCurrentValidationErrors([]); }
      }
    } catch (err: any) { alert(err.message); }
  };

  const handleClearAll = async (filter?: string) => {
    const label = filter === 'requires_review' ? 'all documents requiring review'
                : filter === 'failed'          ? 'all failed documents'
                :                               'ALL documents';
    if (!window.confirm(`Clear ${label}? This cannot be undone.`)) return;
    setIsClearing(true);
    try {
      await ApiClient.delete(`/api/v1/documents/clear?status=${filter || 'all'}`);
      const docs = await fetchDocuments();
      if (docs.length > 0) loadDocResult(docs[0].document_id, docs[0].filename);
      else { setSelectedDocId(null); setCurrentInvoice(BLANK_INVOICE); setCurrentValidationErrors([]); }
    } catch (err: any) { alert(err.message); }
    finally { setIsClearing(false); }
  };

  const handleSaveCorrections = async () => {
    if (!selectedDocId) { setIsEditing(false); return; }
    try {
      await ApiClient.patch(`/api/v1/documents/${selectedDocId}/corrections`, {
        corrections: {
          supplier_name: currentInvoice.supplier_name,
          invoice_number: currentInvoice.invoice_number,
          purchase_order_number: currentInvoice.purchase_order_number,
          subtotal: currentInvoice.subtotal,
          tax: currentInvoice.tax,
          total: currentInvoice.total,
        },
        corrected_by: 'QA Engineer',
      });
      await loadDocResult(selectedDocId, currentDocName);
      await fetchDocuments();
      setIsEditing(false);
      setSaveNotice(true);
      setTimeout(() => setSaveNotice(false), 3000);
    } catch (err: any) { alert(`Save failed: ${err.message}`); }
  };

  // ── Search ─────────────────────────────────────────────────────────────────

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    setSearchResults([]);
    try {
      const res: any = await ApiClient.post('/api/v1/documents/search', {
        query: searchQuery,
        search_type: searchMode,
        limit: 20,
      });
      setSearchResults(Array.isArray(res) ? res : res.results || []);
    } catch (err: any) { alert(`Search failed: ${err.message}`); }
    finally { setIsSearching(false); }
  };

  // ── Verify ─────────────────────────────────────────────────────────────────

  const handleVerify = async () => {
    if (!verifyDocA || !verifyDocB) { alert('Select both documents to compare.'); return; }
    setIsVerifying(true);
    setVerifyResult(null);
    try {
      const res = await ApiClient.post(
        `/api/v1/documents/cross-verify?doc_id_a=${verifyDocA}&doc_id_b=${verifyDocB}`
      );
      setVerifyResult(res);
    } catch (err: any) { alert(`Cross-verification failed: ${err.message}`); }
    finally { setIsVerifying(false); }
  };

  // ── Evaluate ───────────────────────────────────────────────────────────────

  const handleEvaluate = async () => {
    setIsEvaluating(true);
    try {
      const res: any = await ApiClient.post(`/api/v1/documents/dataset/evaluate?sample_size=${evalSampleSize}`);
      setEvalReport(res);
    } catch (e: any) { alert(`Benchmark failed: ${e.message}`); }
    finally { setIsEvaluating(false); }
  };

  // ── Math invariant ─────────────────────────────────────────────────────────

  const lineTotal = currentInvoice.line_items.reduce((s, i) => s + (i.amount || 0), 0);
  const mathOk =
    (currentInvoice.line_items.length === 0 || currentInvoice.subtotal === null ||
      Math.abs(lineTotal - (currentInvoice.subtotal || 0)) < 0.05) &&
    (currentInvoice.total === null || currentInvoice.subtotal === null ||
      Math.abs((currentInvoice.subtotal || 0) + (currentInvoice.tax || 0) - (currentInvoice.total || 0)) < 0.05);

  // ── Derived queue list ─────────────────────────────────────────────────────

  const filteredDocs = documents.filter(d => {
    const q = queueSearch.toLowerCase();
    const matchQ = !q || d.filename.toLowerCase().includes(q) ||
      (d.supplier_name?.toLowerCase().includes(q)) ||
      (d.invoice_number?.toLowerCase().includes(q));
    const matchF = queueFilter === 'all' || d.status === queueFilter;
    return matchQ && matchF;
  });

  const counts = {
    all: documents.length,
    completed: documents.filter(d => d.status === 'completed').length,
    requires_review: documents.filter(d => d.status === 'requires_review').length,
    failed: documents.filter(d => d.status === 'failed').length,
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════════════════════

  return (
    <div className="flex h-full gap-3">
      {/* ── LEFT SIDEBAR NAV ───────────────────────────────────────────────── */}
      <aside className="w-52 shrink-0 bg-[#111116] border border-gray-800 rounded-xl flex flex-col overflow-hidden">
        {/* Nav Items */}
        <nav className="p-2 space-y-1 border-b border-gray-800">
          {NAV_ITEMS.map(nav => (
            <button
              key={nav.id}
              onClick={() => setActiveView(nav.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all group ${
                activeView === nav.id
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                  : 'text-gray-400 hover:bg-gray-800/60 hover:text-gray-200'
              }`}
            >
              <span className={activeView === nav.id ? 'text-white' : 'text-gray-500 group-hover:text-gray-300'}>
                {nav.icon}
              </span>
              <div>
                <p className="text-xs font-semibold leading-tight">{nav.label}</p>
                <p className={`text-[9px] leading-tight ${activeView === nav.id ? 'text-indigo-200' : 'text-gray-600'}`}>
                  {nav.desc}
                </p>
              </div>
            </button>
          ))}
        </nav>

        {/* Quick Upload Button */}
        <div className="p-2 border-b border-gray-800">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white text-xs font-semibold transition-all disabled:opacity-50 shadow shadow-indigo-600/30"
          >
            {isUploading ? <RefreshCw size={13} className="animate-spin" /> : <UploadCloud size={13} />}
            {isUploading ? 'Uploading…' : 'Upload Documents'}
          </button>
          <input
            ref={fileInputRef} type="file" multiple className="hidden"
            accept=".pdf,.tif,.tiff,.jpg,.jpeg,.png,.xlsx,.xls,.csv"
            onChange={e => handleUpload(e.target.files)}
          />
        </div>

        {/* Document Queue Summary */}
        <div className="p-2 flex-1 flex flex-col overflow-hidden">
          <p className="text-[10px] font-bold text-gray-500 uppercase tracking-wider px-1 mb-1.5">Queue Summary</p>
          <div className="grid grid-cols-2 gap-1 mb-2">
            {([['all', 'Total', 'text-gray-300'], ['completed', 'Done', 'text-emerald-400'],
               ['requires_review', 'Review', 'text-amber-400'], ['failed', 'Failed', 'text-rose-400']] as const).map(
              ([key, label, cls]) => (
                <button
                  key={key}
                  onClick={() => setQueueFilter(key)}
                  className={`flex flex-col items-center p-1.5 rounded-lg border transition-all text-center ${
                    queueFilter === key ? 'border-indigo-500 bg-indigo-500/10' : 'border-gray-800 bg-[#151520] hover:border-gray-700'
                  }`}
                >
                  <span className={`text-sm font-bold font-mono ${cls}`}>{counts[key]}</span>
                  <span className="text-[9px] text-gray-500">{label}</span>
                </button>
              )
            )}
          </div>

          {/* Clear Buttons */}
          <div className="space-y-1">
            <button
              onClick={() => handleClearAll('requires_review')}
              disabled={isClearing || counts.requires_review === 0}
              className="w-full flex items-center justify-between gap-1 px-2 py-1.5 rounded-lg text-[10px] bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/25 disabled:opacity-40 transition-colors"
            >
              <span className="flex items-center gap-1"><Trash2 size={10} /> Clear Review</span>
              <span className="font-mono font-bold">{counts.requires_review}</span>
            </button>
            <button
              onClick={() => handleClearAll('failed')}
              disabled={isClearing || counts.failed === 0}
              className="w-full flex items-center justify-between gap-1 px-2 py-1.5 rounded-lg text-[10px] bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/25 disabled:opacity-40 transition-colors"
            >
              <span className="flex items-center gap-1"><Trash2 size={10} /> Clear Failed</span>
              <span className="font-mono font-bold">{counts.failed}</span>
            </button>
            <button
              onClick={() => handleClearAll()}
              disabled={isClearing || counts.all === 0}
              className="w-full flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg text-[10px] bg-gray-500/10 hover:bg-gray-500/20 text-gray-400 border border-gray-700 disabled:opacity-40 transition-colors"
            >
              <Trash2 size={10} /> Clear All ({counts.all})
            </button>
          </div>
        </div>

        {/* Benchmark Samples */}
        <div className="p-2 border-t border-gray-800">
          <p className="text-[10px] font-bold text-gray-500 uppercase tracking-wider px-1 mb-1.5 flex items-center gap-1">
            <Sparkles size={10} className="text-amber-400" /> Test Samples
          </p>
          <div className="space-y-0.5">
            {SAMPLE_FILES.map(s => (
              <button
                key={s.name}
                onClick={() => handleLoadSample(s.name)}
                title={s.label}
                className="w-full flex items-center gap-1.5 px-2 py-1 rounded text-[9px] font-mono bg-[#171720] hover:bg-indigo-600/20 hover:text-indigo-300 text-gray-400 border border-transparent hover:border-indigo-500/30 transition-all truncate text-left"
              >
                <FileIcon type={s.icon} />
                <span className="truncate">{s.name}</span>
              </button>
            ))}
          </div>
          {datasetStats && (
            <p className="text-[9px] text-gray-600 mt-1.5 text-center">
              {datasetStats.total_documents} benchmark files available
            </p>
          )}
        </div>
      </aside>

      {/* ── MAIN CONTENT ───────────────────────────────────────────────────── */}
      <div className="flex-1 min-w-0 flex flex-col gap-3">

        {/* ─── VIEW: PROCESS ─────────────────────────────────────────────── */}
        {activeView === 'process' && (
          <div className="flex-1 flex gap-3 overflow-hidden">
            {/* Document Queue List */}
            <div className="w-64 shrink-0 bg-[#111116] border border-gray-800 rounded-xl flex flex-col overflow-hidden">
              <div className="p-3 border-b border-gray-800 flex items-center justify-between">
                <span className="text-xs font-bold text-gray-200">Document Queue</span>
                <button onClick={fetchDocuments} title="Refresh" className="text-gray-500 hover:text-gray-300 transition-colors">
                  <RefreshCw size={12} />
                </button>
              </div>

              {/* Filter tabs */}
              <div className="flex gap-0.5 p-2 bg-[#0D0D11]">
                {(['all', 'completed', 'requires_review', 'failed'] as const).map(f => (
                  <button
                    key={f}
                    onClick={() => setQueueFilter(f)}
                    className={`flex-1 py-1 rounded text-[9px] font-semibold capitalize transition-all ${
                      queueFilter === f
                        ? f === 'completed'       ? 'bg-emerald-600 text-white'
                        : f === 'requires_review' ? 'bg-amber-600 text-white'
                        : f === 'failed'          ? 'bg-rose-600 text-white'
                        :                          'bg-indigo-600 text-white'
                        : 'text-gray-500 hover:text-gray-300'
                    }`}
                  >
                    {f === 'requires_review' ? 'Review' : f === 'all' ? `All ${counts.all}` : f === 'completed' ? `✓${counts.completed}` : `✗${counts.failed}`}
                  </button>
                ))}
              </div>

              {/* Search */}
              <div className="px-2 pb-2">
                <div className="relative">
                  <Search size={11} className="absolute left-2.5 top-2 text-gray-600" />
                  <input
                    type="text" placeholder="Filter by name, vendor…"
                    value={queueSearch} onChange={e => setQueueSearch(e.target.value)}
                    className="w-full bg-[#161620] border border-gray-800 rounded pl-7 pr-2 py-1.5 text-[10px] text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500/60"
                  />
                </div>
              </div>

              {/* List */}
              <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
                {filteredDocs.length > 0 ? filteredDocs.map(doc => (
                  <div
                    key={doc.document_id}
                    onClick={() => loadDocResult(doc.document_id, doc.filename)}
                    className={`group p-2 rounded-lg border cursor-pointer transition-all ${
                      selectedDocId === doc.document_id
                        ? 'border-indigo-500 bg-indigo-500/10'
                        : 'border-gray-800 bg-[#15151E] hover:border-gray-700'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="flex items-center gap-1 min-w-0">
                        <FileIcon type={doc.file_type} />
                        <span className="text-[10px] font-medium text-gray-200 truncate">{doc.filename}</span>
                      </span>
                      <div className="flex items-center gap-1 shrink-0">
                        <StatusIcon status={doc.status} />
                        <button
                          onClick={e => handleDeleteDoc(doc.document_id, doc.filename, e)}
                          className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-rose-400 transition-opacity"
                        >
                          <Trash2 size={10} />
                        </button>
                      </div>
                    </div>
                    <div className="flex justify-between mt-1 text-[9px] text-gray-500">
                      <span className="truncate">{doc.supplier_name || '—'}</span>
                      {doc.total != null && (
                        <span className="font-mono text-gray-400 shrink-0 ml-1">
                          {doc.currency || '$'}{doc.total.toLocaleString()}
                        </span>
                      )}
                    </div>
                  </div>
                )) : (
                  <div className="flex flex-col items-center justify-center h-32 text-center text-xs text-gray-600 gap-2">
                    <FileText size={28} className="text-gray-700" />
                    <p>No documents.<br />Upload files or load a sample.</p>
                  </div>
                )}
              </div>
            </div>

            {/* Document Viewer */}
            <div className="w-80 shrink-0 bg-[#111116] border border-gray-800 rounded-xl flex flex-col overflow-hidden">
              <div className="p-3 border-b border-gray-800 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-xs font-medium text-gray-200 truncate">{currentDocName}</p>
                  <p className={`text-[9px] capitalize mt-0.5 font-semibold ${
                    currentDocStatus === 'completed' ? 'text-emerald-400'
                    : currentDocStatus === 'requires_review' ? 'text-amber-400'
                    : currentDocStatus === 'failed' ? 'text-rose-400'
                    : 'text-gray-500'
                  }`}>{currentDocStatus.replace('_', ' ')}</p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => setViewMode(v => v === 'visual' ? 'text' : 'visual')}
                    className={`p-1 rounded text-[9px] flex items-center gap-1 transition-all ${
                      viewMode === 'text' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
                    }`}
                    title="Toggle OCR text view"
                  >
                    <Eye size={11} /> {viewMode === 'visual' ? 'OCR' : 'Visual'}
                  </button>
                  <button onClick={() => setZoom(z => Math.max(70, z - 10))} className="text-gray-500 hover:text-white p-1"><ZoomOut size={12} /></button>
                  <span className="text-[9px] font-mono text-gray-500">{zoom}%</span>
                  <button onClick={() => setZoom(z => Math.min(150, z + 10))} className="text-gray-500 hover:text-white p-1"><ZoomIn size={12} /></button>
                </div>
              </div>

              <div className="flex-1 overflow-auto p-3 bg-[#0D0D11]">
                {viewMode === 'visual' ? (
                  <div
                    style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top left' }}
                    className="bg-[#1A1A24] border border-gray-700/60 rounded-lg p-4 space-y-3 shadow-xl min-w-[260px]"
                  >
                    <div className="flex justify-between items-start border-b border-gray-700 pb-2.5">
                      <div>
                        <p className="text-[9px] text-gray-500 uppercase font-semibold tracking-wider">Vendor / Supplier</p>
                        <p className="text-xs font-bold text-indigo-300 mt-0.5">
                          {currentInvoice.supplier_name || <span className="text-gray-600 italic font-normal">Not detected</span>}
                        </p>
                      </div>
                      <div className="text-right">
                        <span className="text-[9px] font-mono font-bold bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded border border-indigo-500/40">
                          {currentInvoice.invoice_number || 'NO INV #'}
                        </span>
                        {currentInvoice.purchase_order_number && (
                          <p className="text-[9px] text-cyan-400 font-mono mt-0.5">
                            PO: {currentInvoice.purchase_order_number}
                          </p>
                        )}
                        <p className="text-[9px] text-gray-500 mt-1">Date: {currentInvoice.invoice_date || '—'}</p>
                      </div>
                    </div>

                    <div>
                      <p className="text-[9px] text-gray-500 uppercase font-semibold">Customer / Bill-to</p>
                      <p className="text-[10px] text-gray-300 mt-0.5">{currentInvoice.customer_name || '—'}</p>
                    </div>

                    {currentInvoice.line_items.length > 0 && (
                      <div className="border border-indigo-500/25 rounded bg-indigo-500/5">
                        <div className="flex justify-between text-[8px] font-bold text-gray-500 uppercase px-2 py-1 border-b border-gray-700/60">
                          <span>Item</span><span>Amount</span>
                        </div>
                        {currentInvoice.line_items.slice(0, 6).map((item, i) => (
                          <div key={i} className="flex justify-between text-[9px] font-mono px-2 py-0.5 text-gray-300">
                            <span className="truncate max-w-[150px]">{item.description}</span>
                            <span>${(item.amount || 0).toLocaleString()}</span>
                          </div>
                        ))}
                        {currentInvoice.line_items.length > 6 && (
                          <p className="text-[8px] text-gray-600 text-center py-0.5">+{currentInvoice.line_items.length - 6} more items</p>
                        )}
                      </div>
                    )}

                    <div className="text-right font-mono space-y-0.5 border-t border-gray-700 pt-2">
                      <div className="flex justify-between text-[9px] text-gray-400">
                        <span>Subtotal</span>
                        <span>${(currentInvoice.subtotal ?? currentInvoice.total ?? 0).toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between text-[9px] text-gray-400">
                        <span>Tax</span>
                        <span>${(currentInvoice.tax ?? 0).toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between text-[10px] font-bold text-emerald-400">
                        <span>Total</span>
                        <span>${(currentInvoice.total ?? 0).toLocaleString()} {currentInvoice.currency}</span>
                      </div>
                    </div>

                    <div className={`flex items-center gap-1.5 text-[9px] rounded px-2 py-1 ${mathOk ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                      {mathOk ? <ShieldCheck size={11} /> : <ShieldAlert size={11} />}
                      {mathOk ? 'Math invariant valid' : 'Calculation discrepancy detected'}
                    </div>
                  </div>
                ) : (
                  <div className="font-mono text-[10px] text-gray-300 whitespace-pre-wrap break-words leading-relaxed select-text">
                    <p className="text-[9px] text-indigo-400 uppercase font-bold mb-2 border-b border-gray-800 pb-1">Raw OCR Text Layer:</p>
                    {currentRawText || <span className="text-gray-600 italic">No OCR text available for this document.</span>}
                  </div>
                )}
              </div>

              <div className="px-3 py-2 border-t border-gray-800 flex items-center justify-between text-[10px] text-gray-500">
                <span className="flex items-center gap-1"><CheckCircle2 size={11} className="text-emerald-500" /> OCR Extracted</span>
                {selectedDocId && (
                  <button onClick={handleRetry} disabled={isRetrying} className="flex items-center gap-1 text-indigo-400 hover:text-indigo-300">
                    <RotateCw size={10} className={isRetrying ? 'animate-spin' : ''} />
                    {isRetrying ? 'Re-extracting…' : 'Re-extract'}
                  </button>
                )}
              </div>
            </div>

            {/* Extraction Details Panel */}
            <div className="flex-1 bg-[#111116] border border-gray-800 rounded-xl flex flex-col overflow-hidden">
              {/* Panel header */}
              <div className="p-3 border-b border-gray-800 flex items-center justify-between">
                <div>
                  <p className="text-xs font-bold text-gray-200">Extracted Invoice Data</p>
                  <p className="text-[9px] text-gray-500 mt-0.5">AI-extracted fields with math validation</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={mathOk ? 'success' : 'danger'} dot>
                    {mathOk ? 'Math Valid' : 'Discrepancy'}
                  </Badge>
                  <Badge variant="primary">
                    {((currentInvoice.confidence_score || 0) * 100).toFixed(0)}% Conf.
                  </Badge>
                  <Button
                    size="sm"
                    variant={isEditing ? 'primary' : 'secondary'}
                    onClick={() => isEditing ? handleSaveCorrections() : setIsEditing(true)}
                    className="text-[10px] flex items-center gap-1"
                  >
                    {isEditing ? <><Save size={11} /> Save</> : <><Edit3 size={11} /> Correct</>}
                  </Button>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-3 space-y-3">
                {/* Save toast */}
                {saveNotice && (
                  <div className="flex items-center gap-2 p-2 bg-emerald-950/50 border border-emerald-500/40 rounded-lg text-xs text-emerald-300">
                    <Check size={13} /> Corrections saved and math re-validated.
                  </div>
                )}

                {/* Validation Errors */}
                {currentValidationErrors.length > 0 && (
                  <div className="p-2.5 bg-amber-950/30 border border-amber-500/30 rounded-lg space-y-1">
                    <div className="flex items-center justify-between">
                      <p className="text-[10px] font-bold text-amber-400 flex items-center gap-1">
                        <ShieldAlert size={12} /> {currentValidationErrors.length} Validation Warning{currentValidationErrors.length > 1 ? 's' : ''}
                      </p>
                      <button onClick={() => setIsEditing(true)} className="text-[9px] text-indigo-400 hover:underline">Fix →</button>
                    </div>
                    {currentValidationErrors.map((err, i) => (
                      <p key={i} className="text-[10px] text-gray-300 pl-4">
                        • <span className="font-semibold text-amber-300">{err.error_type}:</span> {err.message}
                      </p>
                    ))}
                  </div>
                )}

                {/* Editable Fields Grid */}
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: 'Supplier / Vendor', key: 'supplier_name' as const, mono: false },
                    { label: 'Invoice Number', key: 'invoice_number' as const, mono: true },
                    { label: 'Purchase Order (PO) #', key: 'purchase_order_number' as const, mono: true },
                    { label: 'Invoice Date', key: 'invoice_date' as const, mono: true },
                    { label: 'Customer / Bill-to', key: 'customer_name' as const, mono: false },
                    { label: 'Currency', key: 'currency' as const, mono: true },
                  ].map(field => (
                    <div key={field.key} className="p-2.5 bg-[#15151E] border border-gray-800 rounded-lg">
                      <p className="text-[9px] text-gray-500 uppercase font-bold tracking-wider">{field.label}</p>
                      {isEditing && field.key !== 'currency' ? (
                        <input
                          type="text"
                          value={(currentInvoice[field.key] as string) || ''}
                          onChange={e => setCurrentInvoice({ ...currentInvoice, [field.key]: e.target.value })}
                          className={`w-full mt-1 bg-[#1E1E2A] border border-indigo-500/50 rounded px-2 py-1 text-xs text-white focus:outline-none ${field.mono ? 'font-mono' : ''}`}
                        />
                      ) : (
                        <p className={`mt-1 text-xs ${field.mono ? 'font-mono text-indigo-300' : 'text-gray-200'}`}>
                          {(currentInvoice[field.key] as string) || <span className="text-gray-600 italic">—</span>}
                        </p>
                      )}
                    </div>
                  ))}
                </div>

                {/* Line Items Table */}
                <div>
                  <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">Line Items ({currentInvoice.line_items.length})</p>
                  <div className="border border-gray-800 rounded-lg overflow-hidden">
                    <table className="w-full text-left">
                      <thead className="bg-[#15151E] text-[9px] text-gray-500 uppercase border-b border-gray-800">
                        <tr>
                          <th className="px-2 py-1.5">Description</th>
                          <th className="px-2 py-1.5 text-center">Qty</th>
                          <th className="px-2 py-1.5 text-right">Unit Price</th>
                          <th className="px-2 py-1.5 text-right">Amount</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-800/50 text-[10px] font-mono">
                        {currentInvoice.line_items.length > 0 ? currentInvoice.line_items.map((item, i) => (
                          <tr key={i} className="hover:bg-[#161620]">
                            <td className="px-2 py-1 font-sans text-gray-200">{item.description}</td>
                            <td className="px-2 py-1 text-center text-gray-400">{item.quantity ?? 1}</td>
                            <td className="px-2 py-1 text-right text-gray-400">{item.unit_price != null ? `$${item.unit_price.toFixed(2)}` : '—'}</td>
                            <td className="px-2 py-1 text-right text-gray-200 font-semibold">{item.amount != null ? `$${item.amount.toLocaleString()}` : '—'}</td>
                          </tr>
                        )) : (
                          <tr><td colSpan={4} className="px-2 py-4 text-center text-gray-600 italic text-[10px]">No line items extracted</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Math Invariant Summary */}
                <div className="p-3 bg-[#13131C] border border-gray-800 rounded-lg font-mono text-[10px]">
                  <p className="text-gray-500 font-sans uppercase text-[9px] font-bold mb-1.5 tracking-wider">Financial Validation</p>
                  <div className="space-y-1">
                    <div className="flex justify-between text-gray-400">
                      <span>Line Items Sum</span>
                      <span className="text-gray-200">${lineTotal.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between text-gray-400">
                      <span>Subtotal</span>
                      {isEditing ? (
                        <input type="number" value={currentInvoice.subtotal ?? 0}
                          onChange={e => setCurrentInvoice({ ...currentInvoice, subtotal: parseFloat(e.target.value) || 0 })}
                          className="w-24 bg-[#1E1E2A] border border-indigo-500/50 rounded px-1.5 text-right text-white text-[10px]"
                        />
                      ) : <span className="text-gray-200">${(currentInvoice.subtotal ?? currentInvoice.total ?? 0).toLocaleString()}</span>}
                    </div>
                    <div className="flex justify-between text-gray-400">
                      <span>Tax</span>
                      {isEditing ? (
                        <input type="number" value={currentInvoice.tax ?? 0}
                          onChange={e => setCurrentInvoice({ ...currentInvoice, tax: parseFloat(e.target.value) || 0 })}
                          className="w-24 bg-[#1E1E2A] border border-indigo-500/50 rounded px-1.5 text-right text-white text-[10px]"
                        />
                      ) : <span className="text-gray-200">${(currentInvoice.tax ?? 0).toLocaleString()}</span>}
                    </div>
                    <div className="flex justify-between text-gray-200 font-bold border-t border-gray-700 pt-1">
                      <span className="text-gray-300">Total</span>
                      {isEditing ? (
                        <input type="number" value={currentInvoice.total ?? 0}
                          onChange={e => setCurrentInvoice({ ...currentInvoice, total: parseFloat(e.target.value) || 0 })}
                          className="w-24 bg-[#1E1E2A] border border-indigo-500/50 rounded px-1.5 text-right text-emerald-400 font-bold text-[10px]"
                        />
                      ) : <span className="text-emerald-400">${(currentInvoice.total ?? 0).toLocaleString()} {currentInvoice.currency}</span>}
                    </div>
                  </div>
                </div>

                {/* Approve button */}
                <Button
                  variant="primary" size="sm"
                  onClick={() => alert('Document approved and dispatched to ERP ledger!')}
                  className="w-full flex items-center justify-center gap-1.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-semibold"
                >
                  <CheckCircle2 size={13} /> Approve & Dispatch to ERP
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* ─── VIEW: SEARCH ──────────────────────────────────────────────── */}
        {activeView === 'search' && (
          <div className="flex-1 bg-[#111116] border border-gray-800 rounded-xl flex flex-col overflow-hidden">
            {/* Search Header */}
            <div className="p-4 border-b border-gray-800">
              <h2 className="text-sm font-bold text-gray-200 flex items-center gap-2 mb-1">
                <Search size={15} className="text-indigo-400" /> Document Search
              </h2>
              <p className="text-[10px] text-gray-500">
                Keyword, semantic, or hybrid search across all processed documents and extracted invoice fields.
              </p>
            </div>

            {/* Search Controls */}
            <div className="p-4 border-b border-gray-800 space-y-3">
              <div className="flex gap-2">
                <div className="flex-1 relative">
                  <Search size={13} className="absolute left-3 top-2.5 text-gray-500" />
                  <input
                    type="text"
                    placeholder="Search invoice numbers, vendor names, amounts, text content…"
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleSearch()}
                    className="w-full bg-[#15151E] border border-gray-700 rounded-lg pl-9 pr-4 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <Button variant="primary" onClick={handleSearch} disabled={isSearching} className="flex items-center gap-1.5 px-4">
                  {isSearching ? <RefreshCw size={13} className="animate-spin" /> : <Search size={13} />}
                  {isSearching ? 'Searching…' : 'Search'}
                </Button>
              </div>

              <div className="flex gap-2">
                <p className="text-[10px] text-gray-500 flex items-center mr-2">Search Mode:</p>
                {(['keyword', 'semantic', 'hybrid'] as const).map(m => (
                  <button
                    key={m}
                    onClick={() => setSearchMode(m)}
                    className={`px-3 py-1 rounded-full text-[10px] font-semibold capitalize border transition-all ${
                      searchMode === m
                        ? 'bg-indigo-600 text-white border-indigo-500'
                        : 'bg-transparent text-gray-400 border-gray-700 hover:border-gray-500 hover:text-gray-200'
                    }`}
                  >
                    {m === 'hybrid' ? '⚡ Hybrid (Recommended)' : m === 'semantic' ? '🧠 Semantic' : '🔍 Keyword'}
                  </button>
                ))}
              </div>
            </div>

            {/* Search Results */}
            <div className="flex-1 overflow-y-auto p-4">
              {searchResults.length > 0 ? (
                <div className="space-y-2">
                  <p className="text-[10px] text-gray-500 mb-3">{searchResults.length} result{searchResults.length > 1 ? 's' : ''} found</p>
                  {searchResults.map((r: any, i) => (
                    <div
                      key={i}
                      onClick={() => { loadDocResult(r.document_id || r.id, r.filename); setActiveView('process'); }}
                      className="p-3 bg-[#15151E] border border-gray-800 rounded-lg hover:border-indigo-500/50 cursor-pointer transition-all group"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="flex items-center gap-2 text-xs font-medium text-gray-200">
                          <FileIcon type={(r.file_type || r.filename?.split('.').pop() || 'pdf')} />
                          {r.filename}
                        </span>
                        <span className="text-[9px] text-indigo-400 group-hover:text-indigo-300 flex items-center gap-0.5">
                          View <ChevronRight size={10} />
                        </span>
                      </div>
                      {r.snippet && <p className="text-[10px] text-gray-400 leading-relaxed line-clamp-2">{r.snippet}</p>}
                      <div className="flex gap-2 mt-1.5 text-[9px] text-gray-600">
                        {r.invoice_number && <span>Invoice: <span className="text-gray-400 font-mono">{r.invoice_number}</span></span>}
                        {r.supplier_name && <span>Vendor: <span className="text-gray-400">{r.supplier_name}</span></span>}
                        {r.total != null && <span>Total: <span className="text-emerald-400 font-mono">${r.total?.toLocaleString()}</span></span>}
                        {r.score != null && <span className="ml-auto">Score: {(r.score * 100).toFixed(0)}%</span>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center gap-3">
                  <div className="w-16 h-16 rounded-2xl bg-[#15151E] border border-gray-800 flex items-center justify-center">
                    <Search size={28} className="text-gray-700" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-400">Search Document Intelligence</p>
                    <p className="text-xs text-gray-600 mt-1">Enter a query to search across invoices,<br />vendor names, amounts, and OCR text.</p>
                  </div>
                  <div className="flex flex-wrap gap-2 justify-center mt-2">
                    {['Acme Corp', '5000.00', 'VAT invoice', 'Q4 payment'].map(s => (
                      <button key={s} onClick={() => { setSearchQuery(s); }}
                        className="px-3 py-1.5 bg-[#15151E] border border-gray-700 rounded-full text-[10px] text-gray-400 hover:border-indigo-500 hover:text-indigo-300 transition-colors"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ─── VIEW: VERIFY ──────────────────────────────────────────────── */}
        {activeView === 'verify' && (
          <div className="flex-1 bg-[#111116] border border-gray-800 rounded-xl flex flex-col overflow-hidden">
            <div className="p-4 border-b border-gray-800">
              <h2 className="text-sm font-bold text-gray-200 flex items-center gap-2 mb-1">
                <GitCompare size={15} className="text-indigo-400" /> Cross-Document Verification
              </h2>
              <p className="text-[10px] text-gray-500">
                Compare two documents (PDF vs PDF, PDF vs Excel, etc.) to detect discrepancies in extracted financial data.
              </p>
            </div>

            {/* Selector */}
            <div className="p-4 border-b border-gray-800">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[10px] text-gray-500 font-bold uppercase tracking-wider block mb-1.5">Document A (Primary)</label>
                  <select
                    value={verifyDocA}
                    onChange={e => setVerifyDocA(e.target.value)}
                    className="w-full bg-[#15151E] border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-200 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="">Select Document A…</option>
                    {documents.map(d => (
                      <option key={d.document_id} value={d.document_id}>
                        {d.filename} ({d.file_type.toUpperCase()})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-gray-500 font-bold uppercase tracking-wider block mb-1.5">Document B (Comparison)</label>
                  <select
                    value={verifyDocB}
                    onChange={e => setVerifyDocB(e.target.value)}
                    className="w-full bg-[#15151E] border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-200 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="">Select Document B…</option>
                    {documents.filter(d => d.document_id !== verifyDocA).map(d => (
                      <option key={d.document_id} value={d.document_id}>
                        {d.filename} ({d.file_type.toUpperCase()})
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <Button
                variant="primary" onClick={handleVerify} disabled={isVerifying || !verifyDocA || !verifyDocB}
                className="mt-3 flex items-center gap-1.5"
              >
                {isVerifying ? <RefreshCw size={13} className="animate-spin" /> : <GitCompare size={13} />}
                {isVerifying ? 'Cross-Verifying…' : 'Run Cross-Verification'}
              </Button>
            </div>

            {/* Results */}
            <div className="flex-1 overflow-y-auto p-4">
              {verifyResult ? (
                <div className="space-y-3">
                  {/* Score Header */}
                  <div className={`p-3 rounded-lg border flex items-center justify-between ${
                    verifyResult.is_matched
                      ? 'bg-emerald-950/30 border-emerald-500/40'
                      : 'bg-rose-950/30 border-rose-500/40'
                  }`}>
                    <div>
                      <p className="text-sm font-bold text-gray-200">Reconciliation Result</p>
                      <p className="text-[10px] text-gray-400 mt-0.5">{verifyResult.summary}</p>
                    </div>
                    <div className="text-center">
                      <p className={`text-2xl font-bold font-mono ${verifyResult.is_matched ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {(verifyResult.match_score * 100).toFixed(0)}%
                      </p>
                      <p className="text-[9px] text-gray-500">Match Score</p>
                    </div>
                  </div>

                  {/* Discrepancies */}
                  {verifyResult.discrepancies?.length > 0 ? (
                    <div>
                      <p className="text-[10px] font-bold text-rose-400 mb-2">{verifyResult.discrepancies.length} Discrepancies Found:</p>
                      {verifyResult.discrepancies.map((d: any, i: number) => (
                        <div key={i} className="p-2.5 bg-rose-950/20 border border-rose-500/30 rounded-lg mb-1.5 text-xs">
                          <span className="font-bold text-rose-300 uppercase">{d.field}: </span>
                          <span className="text-gray-300">Doc A: </span>
                          <span className="font-mono text-white">{d.doc_a?.value}</span>
                          <span className="text-gray-300"> vs Doc B: </span>
                          <span className="font-mono text-white">{d.doc_b?.value}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="p-3 bg-emerald-950/20 border border-emerald-500/30 rounded-lg flex items-center gap-2 text-xs text-emerald-300">
                      <CheckCircle2 size={15} /> All fields match between the two documents.
                    </div>
                  )}

                  {/* Field table if available */}
                  {verifyResult.field_comparison && (
                    <div className="border border-gray-800 rounded-lg overflow-hidden">
                      <table className="w-full text-xs">
                        <thead className="bg-[#15151E] text-[9px] text-gray-500 uppercase border-b border-gray-800">
                          <tr><th className="px-3 py-2 text-left">Field</th><th className="px-3 py-2">Doc A</th><th className="px-3 py-2">Doc B</th><th className="px-3 py-2 text-right">Status</th></tr>
                        </thead>
                        <tbody className="divide-y divide-gray-800/60">
                          {verifyResult.field_comparison.map((row: any, i: number) => (
                            <tr key={i} className="hover:bg-[#161620]">
                              <td className="px-3 py-1.5 text-gray-300">{row.field}</td>
                              <td className="px-3 py-1.5 font-mono text-center text-gray-200">{row.doc_a_value}</td>
                              <td className="px-3 py-1.5 font-mono text-center text-gray-200">{row.doc_b_value}</td>
                              <td className="px-3 py-1.5 text-right">
                                <span className={`font-bold text-[9px] uppercase ${row.match ? 'text-emerald-400' : 'text-rose-400'}`}>
                                  {row.match ? '✓ Match' : '✗ Mismatch'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center gap-3">
                  <div className="w-16 h-16 rounded-2xl bg-[#15151E] border border-gray-800 flex items-center justify-center">
                    <GitCompare size={28} className="text-gray-700" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-400">PDF vs Excel Cross-Verification</p>
                    <p className="text-xs text-gray-600 mt-1">
                      Upload two documents and run cross-verification<br />to detect financial discrepancies automatically.
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 mt-2 text-[10px] text-gray-500">
                    {['PDF ↔ PDF Invoice', 'PDF ↔ Excel Ledger', 'CSV ↔ XLSX Report', 'TIFF ↔ PDF Scan'].map(pair => (
                      <div key={pair} className="px-3 py-2 bg-[#15151E] border border-gray-800 rounded-lg text-gray-400">{pair}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ─── VIEW: EVALUATE ────────────────────────────────────────────── */}
        {activeView === 'evaluate' && (
          <div className="flex-1 bg-[#111116] border border-gray-800 rounded-xl flex flex-col overflow-hidden">
            <div className="p-4 border-b border-gray-800">
              <h2 className="text-sm font-bold text-gray-200 flex items-center gap-2 mb-1">
                <BarChart3 size={15} className="text-purple-400" /> Task 7 — Benchmark Evaluation
              </h2>
              <p className="text-[10px] text-gray-500">
                Automated evaluation on the labeled benchmark dataset ({datasetStats?.total_documents || 525} documents).
                Measures extraction accuracy, processing time, and failure rates.
              </p>
            </div>

            {/* Controls */}
            <div className="p-4 border-b border-gray-800 flex items-center gap-4">
              <div className="flex items-center gap-2">
                <label className="text-[10px] text-gray-500">Sample Size:</label>
                <select
                  value={evalSampleSize}
                  onChange={e => setEvalSampleSize(Number(e.target.value))}
                  className="bg-[#15151E] border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-indigo-500"
                >
                  {[10, 20, 50, 100].map(n => (
                    <option key={n} value={n}>{n} documents</option>
                  ))}
                </select>
              </div>
              <Button
                variant="primary" onClick={handleEvaluate} disabled={isEvaluating}
                className="flex items-center gap-1.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500"
              >
                {isEvaluating ? <RefreshCw size={13} className="animate-spin" /> : <Activity size={13} />}
                {isEvaluating ? 'Running Benchmark…' : 'Run Evaluation Now'}
              </Button>
              {evalReport && (
                <span className="text-[10px] text-gray-500 ml-auto">
                  Last run: {new Date(evalReport.evaluation_timestamp).toLocaleString()}
                </span>
              )}
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {evalReport ? (
                <div className="space-y-4">
                  {/* KPI Cards */}
                  <div className="grid grid-cols-4 gap-3">
                    {[
                      { label: 'Success Rate', value: `${evalReport.performance_metrics.document_success_rate_percent}%`, sub: 'Documents processed', color: 'text-emerald-400', bg: 'border-emerald-500/30 bg-emerald-500/5', icon: <CheckCircle2 size={18} className="text-emerald-500" /> },
                      { label: 'Failure Rate', value: `${evalReport.performance_metrics.document_failure_rate_percent}%`, sub: 'Processing errors', color: 'text-rose-400', bg: 'border-rose-500/30 bg-rose-500/5', icon: <XCircle size={18} className="text-rose-500" /> },
                      { label: 'Avg Processing', value: `${evalReport.performance_metrics.average_processing_time_ms}ms`, sub: 'Per document OCR+AI', color: 'text-indigo-400', bg: 'border-indigo-500/30 bg-indigo-500/5', icon: <Clock size={18} className="text-indigo-500" /> },
                      { label: 'Review Rate', value: `${evalReport.performance_metrics.manual_review_rate_percent}%`, sub: 'Needs human review', color: 'text-amber-400', bg: 'border-amber-500/30 bg-amber-500/5', icon: <AlertTriangle size={18} className="text-amber-500" /> },
                    ].map(kpi => (
                      <div key={kpi.label} className={`p-3 rounded-xl border ${kpi.bg}`}>
                        <div className="flex items-start justify-between mb-2">
                          {kpi.icon}
                          <span className={`text-2xl font-bold font-mono ${kpi.color}`}>{kpi.value}</span>
                        </div>
                        <p className="text-[10px] font-semibold text-gray-300">{kpi.label}</p>
                        <p className="text-[9px] text-gray-600">{kpi.sub}</p>
                      </div>
                    ))}
                  </div>

                  {/* Field Accuracy */}
                  <div className="p-4 bg-[#13131C] border border-gray-800 rounded-xl">
                    <div className="flex items-center justify-between mb-3">
                      <p className="text-xs font-bold text-gray-200 flex items-center gap-2">
                        <TrendingUp size={14} className="text-purple-400" /> Field-Level Extraction Accuracy
                      </p>
                      <span className={`text-lg font-bold font-mono ${
                        evalReport.field_extraction_accuracy.overall_accuracy_percent >= 80 ? 'text-emerald-400'
                        : evalReport.field_extraction_accuracy.overall_accuracy_percent >= 60 ? 'text-amber-400'
                        : 'text-rose-400'
                      }`}>
                        {evalReport.field_extraction_accuracy.overall_accuracy_percent}%
                      </span>
                    </div>

                    {/* Overall progress bar */}
                    <div className="w-full bg-gray-800 rounded-full h-2 mb-4">
                      <div
                        className={`h-2 rounded-full transition-all ${
                          evalReport.field_extraction_accuracy.overall_accuracy_percent >= 80 ? 'bg-emerald-500'
                          : evalReport.field_extraction_accuracy.overall_accuracy_percent >= 60 ? 'bg-amber-500'
                          : 'bg-rose-500'
                        }`}
                        style={{ width: `${evalReport.field_extraction_accuracy.overall_accuracy_percent}%` }}
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { label: 'Invoice Number', value: evalReport.field_extraction_accuracy.invoice_number_accuracy_percent },
                        { label: 'Supplier Name', value: evalReport.field_extraction_accuracy.supplier_name_accuracy_percent },
                        { label: 'Total Amount', value: evalReport.field_extraction_accuracy.total_amount_accuracy_percent },
                        { label: 'Invoice Date', value: evalReport.field_extraction_accuracy.invoice_date_accuracy_percent },
                      ].map(f => (
                        <div key={f.label}>
                          <div className="flex justify-between text-[10px] mb-1">
                            <span className="text-gray-400">{f.label}</span>
                            <span className="font-mono font-bold text-gray-200">{f.value}%</span>
                          </div>
                          <div className="w-full bg-gray-800 rounded-full h-1.5">
                            <div
                              className={`h-1.5 rounded-full ${f.value >= 80 ? 'bg-emerald-500' : f.value >= 60 ? 'bg-amber-500' : 'bg-rose-500'}`}
                              style={{ width: `${f.value}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Processing Time Stats */}
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { label: 'Min Processing Time', value: `${evalReport.performance_metrics.min_processing_time_ms}ms` },
                      { label: 'Avg Processing Time', value: `${evalReport.performance_metrics.average_processing_time_ms}ms` },
                      { label: 'Max Processing Time', value: `${evalReport.performance_metrics.max_processing_time_ms}ms` },
                    ].map(s => (
                      <div key={s.label} className="p-3 bg-[#13131C] border border-gray-800 rounded-lg text-center">
                        <p className="text-xs font-bold font-mono text-indigo-400">{s.value}</p>
                        <p className="text-[9px] text-gray-500 mt-0.5">{s.label}</p>
                      </div>
                    ))}
                  </div>

                  {/* Dataset info */}
                  <div className="p-3 bg-[#13131C] border border-gray-800 rounded-lg flex items-center justify-between text-[10px] text-gray-500">
                    <span>Evaluated: <strong className="text-gray-300">{evalReport.dataset.evaluated_sample_size}</strong> documents</span>
                    <span>Total available: <strong className="text-gray-300">{evalReport.dataset.total_available_in_dataset}</strong></span>
                    <span>Benchmark dataset: <code className="text-gray-400">uploads/</code></span>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center gap-4">
                  <div className="w-20 h-20 rounded-2xl bg-purple-950/30 border border-purple-500/20 flex items-center justify-center">
                    <BarChart3 size={36} className="text-purple-600" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-300">Benchmark Evaluation Ready</p>
                    <p className="text-xs text-gray-600 mt-1">
                      Run automated evaluation against {datasetStats?.total_documents || 525} labeled<br />
                      benchmark documents to measure system accuracy.
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-[10px] text-gray-500 max-w-sm">
                    {['Extraction Accuracy', 'Processing Speed', 'Success / Failure Rate', 'Field-Level Metrics'].map(m => (
                      <div key={m} className="flex items-center gap-1.5 p-2 bg-[#15151E] border border-gray-800 rounded-lg">
                        <X size={10} className="text-gray-700" />{m}
                      </div>
                    ))}
                  </div>
                  <Button
                    variant="primary" onClick={handleEvaluate} disabled={isEvaluating}
                    className="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 flex items-center gap-2"
                  >
                    <Activity size={14} /> Run Benchmark Evaluation
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
