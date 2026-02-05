'use client';

import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

interface StreamingStep {
  id: string;
  label: string;
  status: 'pending' | 'active' | 'done';
}

interface AskStreamingOverlayProps {
  isStreaming: boolean;
  currentStep?: string;
  steps?: Array<{ id: string; title: string; status?: string }>;
}

const DEFAULT_STEPS: StreamingStep[] = [
  { id: 'analyze', label: 'Analisando', status: 'pending' },
  { id: 'search', label: 'Pesquisando', status: 'pending' },
  { id: 'generate', label: 'Gerando', status: 'pending' },
];

export function AskStreamingOverlay({
  isStreaming,
  currentStep,
  steps = [],
}: AskStreamingOverlayProps) {
  const [localSteps, setLocalSteps] = useState<StreamingStep[]>(DEFAULT_STEPS);
  const [dots, setDots] = useState('');

  // Animate dots
  useEffect(() => {
    if (!isStreaming) return;
    const interval = setInterval(() => {
      setDots((d) => (d.length >= 3 ? '' : d + '.'));
    }, 400);
    return () => clearInterval(interval);
  }, [isStreaming]);

  // Update steps from props
  useEffect(() => {
    if (steps.length > 0) {
      setLocalSteps(
        steps.map((s) => ({
          id: s.id,
          label: s.title,
          status: s.status === 'done' ? 'done' : s.status === 'running' ? 'active' : 'pending',
        }))
      );
    } else if (currentStep) {
      // Simple step progression based on currentStep string
      setLocalSteps((prev) =>
        prev.map((step) => {
          if (currentStep.toLowerCase().includes('analis')) {
            return { ...step, status: step.id === 'analyze' ? 'active' : step.status };
          }
          if (currentStep.toLowerCase().includes('pesquis') || currentStep.toLowerCase().includes('busca')) {
            return {
              ...step,
              status:
                step.id === 'analyze'
                  ? 'done'
                  : step.id === 'search'
                  ? 'active'
                  : step.status,
            };
          }
          if (currentStep.toLowerCase().includes('gera') || currentStep.toLowerCase().includes('escrev')) {
            return {
              ...step,
              status:
                step.id === 'analyze' || step.id === 'search'
                  ? 'done'
                  : step.id === 'generate'
                  ? 'active'
                  : step.status,
            };
          }
          return step;
        })
      );
    }
  }, [steps, currentStep]);

  // Reset when not streaming
  useEffect(() => {
    if (!isStreaming) {
      const timeout = setTimeout(() => {
        setLocalSteps(DEFAULT_STEPS);
      }, 1000);
      return () => clearTimeout(timeout);
    }
  }, [isStreaming]);

  const activeStep = localSteps.find((s) => s.status === 'active');

  return (
    <AnimatePresence>
      {isStreaming && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.2 }}
          className="flex items-center gap-4 px-4 py-3 rounded-xl bg-gradient-to-r from-slate-50 to-slate-100/80 dark:from-slate-900 dark:to-slate-800/80 border border-slate-200/60 dark:border-slate-700/60 shadow-sm"
        >
          {/* Animated pulse indicator */}
          <div className="relative flex items-center justify-center">
            <div className="absolute w-8 h-8 rounded-full bg-indigo-500/20 animate-ping" />
            <div className="relative w-4 h-4 rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 shadow-lg shadow-indigo-500/30" />
          </div>

          {/* Steps indicator */}
          <div className="flex items-center gap-1">
            {localSteps.map((step, idx) => (
              <div key={step.id} className="flex items-center">
                <motion.div
                  className={cn(
                    'w-2 h-2 rounded-full transition-all duration-300',
                    step.status === 'done' && 'bg-emerald-500',
                    step.status === 'active' && 'bg-indigo-500 scale-125',
                    step.status === 'pending' && 'bg-slate-300 dark:bg-slate-600'
                  )}
                  animate={step.status === 'active' ? { scale: [1, 1.3, 1] } : {}}
                  transition={{ duration: 0.8, repeat: Infinity }}
                />
                {idx < localSteps.length - 1 && (
                  <div
                    className={cn(
                      'w-6 h-0.5 mx-1 transition-colors duration-300',
                      step.status === 'done' ? 'bg-emerald-500' : 'bg-slate-200 dark:bg-slate-700'
                    )}
                  />
                )}
              </div>
            ))}
          </div>

          {/* Current action text */}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">
              {activeStep?.label || 'Processando'}
              <span className="text-slate-400 dark:text-slate-500 w-6 inline-block">
                {dots}
              </span>
            </p>
          </div>

          {/* Subtle shimmer effect */}
          <div className="absolute inset-0 rounded-xl overflow-hidden pointer-events-none">
            <motion.div
              className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent"
              animate={{ x: ['-100%', '100%'] }}
              transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
            />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
