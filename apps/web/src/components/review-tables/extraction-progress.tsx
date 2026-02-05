'use client';

import * as React from 'react';
import { useState, useCallback, useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Play,
  Pause,
  X,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  CheckCircle2,
  Loader2,
  FileText,
  Clock,
} from 'lucide-react';
import apiClient from '@/lib/api-client';
import { useReviewTableStore } from '@/stores/review-table-store';
import type { ExtractionJob } from '@/types/review-table';

interface ExtractionProgressProps {
  tableId: string;
  job: ExtractionJob;
  onJobComplete?: () => void;
  className?: string;
}

const formatTime = (seconds: number): string => {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${minutes}m ${secs}s`;
};

export function ExtractionProgress({
  tableId,
  job,
  onJobComplete,
  className,
}: ExtractionProgressProps) {
  const { setActiveJob } = useReviewTableStore();
  const [isExpanded, setIsExpanded] = useState(false);
  const [isPausing, setIsPausing] = useState(false);
  const [isResuming, setIsResuming] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [estimatedTimeRemaining, setEstimatedTimeRemaining] = useState<number | null>(
    null
  );
  const [startTime] = useState(Date.now());

  // Use ref to avoid re-running useEffect when callback changes
  const onJobCompleteRef = useRef(onJobComplete);
  onJobCompleteRef.current = onJobComplete;

  // Calculate progress
  const progress =
    job.total_documents > 0
      ? (job.processed_documents / job.total_documents) * 100
      : 0;

  const isRunning = job.status === 'running';
  const isPaused = job.status === 'paused';
  const isCompleted = job.status === 'completed';
  const hasErrors = job.error_count > 0;

  // Estimate time remaining based on current progress rate
  useEffect(() => {
    if (!isRunning || job.processed_documents === 0) {
      setEstimatedTimeRemaining(null);
      return;
    }

    const elapsed = (Date.now() - startTime) / 1000;
    const rate = job.processed_documents / elapsed;
    const remaining = job.total_documents - job.processed_documents;
    const estimate = remaining / rate;

    setEstimatedTimeRemaining(estimate);
  }, [isRunning, job.processed_documents, job.total_documents, startTime]);

  // Poll for job updates
  useEffect(() => {
    if (isCompleted || job.status === 'error' || job.status === 'cancelled') {
      onJobCompleteRef.current?.();
      return;
    }

    const pollInterval = setInterval(async () => {
      try {
        const updatedJob = await apiClient.getExtractionJob(tableId, job.id);
        setActiveJob(updatedJob);

        if (
          updatedJob.status === 'completed' ||
          updatedJob.status === 'error' ||
          updatedJob.status === 'cancelled'
        ) {
          onJobCompleteRef.current?.();
        }
      } catch (error) {
        console.error('Error polling job status:', error);
      }
    }, 2000);

    return () => clearInterval(pollInterval);
  }, [tableId, job.id, job.status, isCompleted, setActiveJob]);

  const handlePause = useCallback(async () => {
    setIsPausing(true);
    try {
      await apiClient.pauseExtractionJob(tableId, job.id);
      setActiveJob({ ...job, status: 'paused' });
    } catch (error) {
      console.error('Error pausing job:', error);
    } finally {
      setIsPausing(false);
    }
  }, [tableId, job, setActiveJob]);

  const handleResume = useCallback(async () => {
    setIsResuming(true);
    try {
      await apiClient.resumeExtractionJob(tableId, job.id);
      setActiveJob({ ...job, status: 'running' });
    } catch (error) {
      console.error('Error resuming job:', error);
    } finally {
      setIsResuming(false);
    }
  }, [tableId, job, setActiveJob]);

  const handleCancel = useCallback(async () => {
    setIsCancelling(true);
    try {
      await apiClient.cancelExtractionJob(tableId, job.id);
      setActiveJob({ ...job, status: 'cancelled' });
      onJobCompleteRef.current?.();
    } catch (error) {
      console.error('Error cancelling job:', error);
    } finally {
      setIsCancelling(false);
    }
  }, [tableId, job, setActiveJob]);

  // Don't render if job is complete and no errors
  if (isCompleted && !hasErrors) {
    return null;
  }

  return (
    <Collapsible
      open={isExpanded}
      onOpenChange={setIsExpanded}
      className={cn(
        'border rounded-lg bg-card overflow-hidden',
        hasErrors && 'border-yellow-500/50',
        className
      )}
    >
      <div className="p-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            {isRunning && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
            {isPaused && <Pause className="h-4 w-4 text-yellow-600" />}
            {isCompleted && <CheckCircle2 className="h-4 w-4 text-green-600" />}
            {job.status === 'error' && (
              <AlertCircle className="h-4 w-4 text-destructive" />
            )}
            <span className="font-medium text-sm">
              {isRunning && 'Extraindo dados...'}
              {isPaused && 'Extracao pausada'}
              {isCompleted && 'Extracao concluida'}
              {job.status === 'error' && 'Erro na extracao'}
              {job.status === 'cancelled' && 'Extracao cancelada'}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Status badges */}
            {hasErrors && (
              <Badge variant="secondary" className="text-yellow-600">
                <AlertCircle className="h-3 w-3 mr-1" />
                {job.error_count} erros
              </Badge>
            )}

            {/* Time remaining */}
            {isRunning && estimatedTimeRemaining && (
              <Badge variant="secondary" className="text-xs">
                <Clock className="h-3 w-3 mr-1" />
                ~{formatTime(estimatedTimeRemaining)}
              </Badge>
            )}

            {/* Actions */}
            <div className="flex items-center gap-1">
              {isRunning && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={handlePause}
                  disabled={isPausing}
                >
                  {isPausing ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Pause className="h-4 w-4" />
                  )}
                </Button>
              )}
              {isPaused && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={handleResume}
                  disabled={isResuming}
                >
                  {isResuming ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                </Button>
              )}
              {(isRunning || isPaused) && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-destructive"
                  onClick={handleCancel}
                  disabled={isCancelling}
                >
                  {isCancelling ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <X className="h-4 w-4" />
                  )}
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Progress bar */}
        <div className="space-y-2">
          <Progress value={progress} className="h-2" />
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {job.processed_documents} de {job.total_documents} documentos
            </span>
            <span>{Math.round(progress)}%</span>
          </div>
        </div>

        {/* Expand button for errors */}
        {hasErrors && (
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="w-full mt-2 text-xs text-muted-foreground"
            >
              {isExpanded ? (
                <>
                  <ChevronUp className="h-4 w-4 mr-1" />
                  Ocultar detalhes
                </>
              ) : (
                <>
                  <ChevronDown className="h-4 w-4 mr-1" />
                  Ver {job.error_count} erros
                </>
              )}
            </Button>
          </CollapsibleTrigger>
        )}
      </div>

      {/* Error details */}
      <CollapsibleContent>
        <div className="border-t">
          <ScrollArea className="max-h-48">
            <div className="p-4 space-y-2">
              {job.errors?.map((error, index) => (
                <div
                  key={index}
                  className="flex items-start gap-2 p-2 bg-muted/50 rounded text-xs"
                >
                  <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <p className="font-medium truncate">
                      Documento: {error.document_id}
                    </p>
                    <p className="text-destructive">{error.error}</p>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

// Minimal version for inline display
export function ExtractionProgressInline({
  job,
}: {
  job: ExtractionJob | null;
}) {
  if (!job || job.status === 'completed' || job.status === 'cancelled') {
    return null;
  }

  const progress =
    job.total_documents > 0
      ? (job.processed_documents / job.total_documents) * 100
      : 0;

  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <Loader2 className="h-3 w-3 animate-spin" />
      <Progress value={progress} className="h-1 w-20" />
      <span>{Math.round(progress)}%</span>
    </div>
  );
}
