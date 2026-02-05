'use client';

import { useState, useCallback, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Play,
  Loader2,
  BookCheck,
  FileSearch,
  Upload,
  FileText,
  CheckCircle2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { PlaybookAnalysisPanel } from '../../components/playbook-analysis-panel';
import {
  type PlaybookAnalysis,
  AREA_LABELS,
  usePlaybook,
  useRunPlaybookAnalysis,
  usePlaybookAnalyses,
  usePlaybookAnalysis,
} from '../../hooks';

// TODO: Replace with actual documents from a useDocuments() hook or API call
const AVAILABLE_DOCUMENTS: { id: string; name: string; type: string; date: string }[] = [];

export default function PlaybookAnalyzePage() {
  const params = useParams();
  const router = useRouter();
  const playbookId = params.id as string;

  const { data: playbook, isLoading: playbookLoading } = usePlaybook(playbookId);
  const { data: pastAnalyses } = usePlaybookAnalyses(playbookId);
  const runAnalysis = useRunPlaybookAnalysis();

  const [selectedDocId, setSelectedDocId] = useState<string>('');
  const [searchDoc, setSearchDoc] = useState('');
  const [currentAnalysis, setCurrentAnalysis] = useState<PlaybookAnalysis | null>(null);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);

  // Load a specific saved analysis when selected from history
  const { data: savedAnalysis } = usePlaybookAnalysis(
    selectedAnalysisId ? playbookId : undefined,
    selectedAnalysisId ?? undefined
  );

  // When saved analysis loads, set it as current
  const handleLoadSavedAnalysis = useCallback((analysis: PlaybookAnalysis) => {
    // If we have a real ID, fetch from API to get full data including reviewed_clauses
    if (analysis.id && !analysis.id.startsWith('analysis-')) {
      setSelectedAnalysisId(analysis.id);
    } else {
      setCurrentAnalysis(analysis);
    }
  }, []);

  // Sync savedAnalysis into currentAnalysis
  useEffect(() => {
    if (savedAnalysis && selectedAnalysisId && (!currentAnalysis || currentAnalysis.id !== savedAnalysis.id)) {
      setCurrentAnalysis(savedAnalysis);
    }
  }, [savedAnalysis, selectedAnalysisId, currentAnalysis]);

  const handleAnalysisUpdated = useCallback((updated: PlaybookAnalysis) => {
    setCurrentAnalysis(updated);
  }, []);

  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadedFile(file);
      // TODO: Send file to API when backend is ready
      toast.success(`Arquivo "${file.name}" selecionado`);
    }
    e.target.value = '';
  }, []);

  const filteredDocs = AVAILABLE_DOCUMENTS.filter((doc) =>
    doc.name.toLowerCase().includes(searchDoc.toLowerCase())
  );

  const handleRunAnalysis = async () => {
    if (!selectedDocId) {
      toast.error('Selecione um documento para analisar');
      return;
    }

    const result = await runAnalysis.mutateAsync({
      playbookId,
      documentId: selectedDocId,
    });

    setCurrentAnalysis(result);
  };

  const handleExport = () => {
    toast.success('Relatorio exportado (funcionalidade em desenvolvimento)');
  };

  if (playbookLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
      </div>
    );
  }

  if (!playbook) {
    return (
      <div className="text-center py-20">
        <BookCheck className="h-12 w-12 text-slate-300 mx-auto mb-4" />
        <p className="text-slate-500 mb-4">Playbook nao encontrado</p>
        <Button variant="outline" onClick={() => router.push('/playbooks')} className="gap-2">
          <ArrowLeft className="h-4 w-4" />
          Voltar
        </Button>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-5xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => router.push(`/playbooks/${playbookId}`)}
          className="shrink-0"
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-800 dark:text-slate-200">
              Analise de Contrato
            </h1>
            <Badge variant="secondary" className="text-[10px]">
              {playbook.name}
            </Badge>
          </div>
          <p className="text-xs text-slate-500">
            {AREA_LABELS[playbook.area]} | {playbook.rules?.length || playbook.rule_count} regra(s) ativa(s)
          </p>
        </div>
      </div>

      {!currentAnalysis && !runAnalysis.isPending && (
        <>
          {/* Document selection */}
          <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5 space-y-4">
            <h3 className="text-sm font-semibold text-slate-600 dark:text-slate-300 flex items-center gap-2">
              <FileSearch className="h-4 w-4" />
              Selecione o Documento para Analise
            </h3>

            <div className="relative">
              <FileSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                value={searchDoc}
                onChange={(e) => setSearchDoc(e.target.value)}
                placeholder="Buscar documento..."
                className="pl-9"
              />
            </div>

            <div className="grid gap-2 max-h-[300px] overflow-y-auto">
              {filteredDocs.map((doc) => (
                <button
                  key={doc.id}
                  onClick={() => setSelectedDocId(doc.id)}
                  className={cn(
                    'flex items-center gap-3 p-3 rounded-lg border text-left transition-all',
                    selectedDocId === doc.id
                      ? 'border-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 dark:border-indigo-600'
                      : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600'
                  )}
                >
                  <FileText className="h-4 w-4 text-slate-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">
                      {doc.name}
                    </p>
                    <p className="text-[10px] text-slate-400">
                      {doc.type} | {new Date(doc.date).toLocaleDateString('pt-BR')}
                    </p>
                  </div>
                  {selectedDocId === doc.id && (
                    <div className="h-2 w-2 rounded-full bg-indigo-500 shrink-0" />
                  )}
                </button>
              ))}
            </div>

            {/* Upload option */}
            <div className="border-t border-slate-100 dark:border-slate-800 pt-4">
              <label className="flex items-center gap-3 p-3 rounded-lg border border-dashed border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 transition-all cursor-pointer text-left">
                <Upload className="h-4 w-4 text-slate-400" />
                <div>
                  <p className="text-sm text-slate-600 dark:text-slate-300">
                    {uploadedFile ? uploadedFile.name : 'Fazer upload de novo documento'}
                  </p>
                  <p className="text-[10px] text-slate-400">
                    {uploadedFile
                      ? `${(uploadedFile.size / 1024).toFixed(1)} KB`
                      : 'PDF, DOCX ou TXT'}
                  </p>
                </div>
                <input type="file" className="hidden" accept=".pdf,.docx,.doc,.txt" onChange={handleFileUpload} />
              </label>
            </div>
          </div>

          {/* Run button */}
          <div className="flex justify-end">
            <Button
              onClick={handleRunAnalysis}
              disabled={!selectedDocId || runAnalysis.isPending}
              className="gap-2 bg-indigo-600 hover:bg-indigo-500 text-white"
            >
              <Play className="h-4 w-4" />
              Executar Analise
            </Button>
          </div>

          {/* Past analyses */}
          {pastAnalyses && pastAnalyses.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-slate-600 dark:text-slate-300">
                Analises Anteriores
              </h3>
              <div className="space-y-2">
                {pastAnalyses.map((analysis) => {
                  const reviewedCount = analysis.reviewed_clauses
                    ? Object.keys(analysis.reviewed_clauses).length
                    : 0;
                  const totalClauses = analysis.results.length;
                  const reviewProgress = totalClauses > 0
                    ? Math.round((reviewedCount / totalClauses) * 100)
                    : 0;

                  return (
                    <button
                      key={analysis.id}
                      onClick={() => handleLoadSavedAnalysis(analysis)}
                      className="w-full flex items-center gap-3 p-3 rounded-lg border border-slate-200 dark:border-slate-700 hover:border-indigo-300 text-left transition-all"
                    >
                      <FileText className="h-4 w-4 text-slate-400" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">
                          {analysis.document_name || `Analise ${analysis.id.slice(0, 8)}`}
                        </p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <p className="text-[10px] text-slate-400">
                            Score: {analysis.risk_score} | {new Date(analysis.created_at).toLocaleString('pt-BR')}
                          </p>
                          {totalClauses > 0 && (
                            <span className="flex items-center gap-1 text-[10px] text-slate-400">
                              <CheckCircle2 className="h-3 w-3 text-green-500" />
                              {reviewedCount}/{totalClauses} revisadas
                            </span>
                          )}
                        </div>
                        {/* Mini review progress bar */}
                        {totalClauses > 0 && (
                          <div className="h-1 w-full rounded-full bg-slate-100 dark:bg-slate-800 mt-1.5 overflow-hidden">
                            <div
                              className="h-full rounded-full bg-green-500 transition-all"
                              style={{ width: `${reviewProgress}%` }}
                            />
                          </div>
                        )}
                      </div>
                      <Badge
                        className={cn(
                          'text-[10px] border-0 shrink-0',
                          analysis.risk_score >= 70
                            ? 'bg-green-100 text-green-700'
                            : analysis.risk_score >= 50
                              ? 'bg-yellow-100 text-yellow-700'
                              : 'bg-red-100 text-red-700'
                        )}
                      >
                        {analysis.risk_score}%
                      </Badge>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}

      {/* Loading state */}
      {runAnalysis.isPending && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-12 text-center space-y-4">
          <div className="relative mx-auto h-16 w-16">
            <div className="absolute inset-0 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 animate-spin [animation-duration:3s] opacity-30" />
            <div className="absolute inset-[3px] rounded-full bg-white dark:bg-slate-900" />
            <div className="absolute inset-0 flex items-center justify-center">
              <FileSearch className="h-6 w-6 text-indigo-500 animate-pulse" />
            </div>
          </div>
          <div>
            <p className="text-lg font-semibold text-slate-800 dark:text-slate-200">
              Analisando documento...
            </p>
            <p className="text-sm text-slate-500 mt-1">
              O playbook esta sendo aplicado clausula por clausula
            </p>
          </div>
        </div>
      )}

      {/* Results */}
      {currentAnalysis && !runAnalysis.isPending && (
        <div className="space-y-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setCurrentAnalysis(null);
              setSelectedAnalysisId(null);
            }}
            className="gap-1.5"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Nova analise
          </Button>
          <PlaybookAnalysisPanel
            analysis={currentAnalysis}
            onExport={handleExport}
            onAnalysisUpdated={handleAnalysisUpdated}
          />
        </div>
      )}
    </div>
  );
}
