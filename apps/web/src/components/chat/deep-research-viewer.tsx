
import { useEffect, useRef, useState } from 'react';
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Brain, Database, CheckCircle2, Loader2, FileText, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface ThinkingStep {
    text: string;
    timestamp: string;
    from_cache?: boolean;
}

interface DeepResearchViewerProps {
    jobId: string;
    isVisible: boolean;
    events: any[]; // Stream of events passed from parent or store
}

export function DeepResearchViewer({ jobId, isVisible, events }: DeepResearchViewerProps) {
    const [steps, setSteps] = useState<ThinkingStep[]>([]);
    const [status, setStatus] = useState<'idle' | 'running' | 'cached' | 'done'>('idle');
    const [isExpanded, setIsExpanded] = useState(true);
    const scrollRef = useRef<HTMLDivElement>(null);

    // Process events
    useEffect(() => {
        if (!isVisible) return;

        // We assume 'events' is an array that grows, or we subscribe to store.
        // Ideally, this component receives the latest state or list of steps.
        // For now, let's assume the parent passes the accumulated events relevant to research.

        // Simple logic: scan events to rebuild state
        let newSteps: ThinkingStep[] = [];
        let currentStatus: any = 'idle';
        let sawAnyResearchSignal = false;
        let sawDone = false;
        let sawCacheHit = false;

        events.forEach(e => {
            if (!e) return;
            // We treat any of these as "research is active/was active"
            if (e.type === 'deep_research_start' || e.type === 'research_start') {
                currentStatus = 'running';
                sawAnyResearchSignal = true;
            }
            if (e.type === 'cache_hit') { currentStatus = 'cached'; sawAnyResearchSignal = true; sawCacheHit = true; }
            if (e.type === 'thinking' || e.type === 'deepresearch_step') {
                const text = typeof e.text === 'string'
                    ? e.text
                    : typeof e.data?.step === 'string'
                        ? e.data.step
                        : '';
                if (text) {
                    newSteps.push({
                        text,
                        timestamp: new Date().toISOString(),
                        from_cache: e.from_cache ?? e.data?.from_cache
                    });
                    sawAnyResearchSignal = true;
                }
            }
            if (e.type === 'deep_research_done' || e.type === 'research_done') { currentStatus = 'done'; sawAnyResearchSignal = true; sawDone = true; }
        });

        // Fallbacks:
        // - If we have a visible job but no explicit "start" event yet, consider "running"
        //   (LangGraph emits node output only on completion in some cases).
        if (!sawAnyResearchSignal && jobId) currentStatus = 'running';
        // - If we got cache_hit but not done, keep "cached" to reflect fast path.
        if (sawCacheHit && !sawDone) currentStatus = 'cached';

        setSteps(newSteps);
        setStatus(currentStatus);

        // Auto-scroll
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }

    }, [events, isVisible, jobId]);

    if (!isVisible || status === 'idle') return null;

    return (
        <Card className="my-4 border-indigo-500/20 bg-indigo-500/5 overflow-hidden">
            <div
                className="flex items-center justify-between p-3 cursor-pointer hover:bg-white/5 transition-colors"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="flex items-center gap-2">
                    {status === 'running' && <Loader2 className="h-4 w-4 text-indigo-400 animate-spin" />}
                    {status === 'cached' && <Database className="h-4 w-4 text-green-400" />}
                    {status === 'done' && <CheckCircle2 className="h-4 w-4 text-indigo-400" />}

                    <span className="text-sm font-medium text-indigo-200">
                        {status === 'cached' ? 'Deep Research (Cache)' : 'Deep Research Agent'}
                    </span>

                    <Badge variant="outline" className="ml-2 border-indigo-500/30 text-[10px] text-indigo-300">
                        {steps.length} passos
                    </Badge>
                </div>

                {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
            </div>

            {isExpanded && (
                <div className="border-t border-indigo-500/10 bg-black/20">
                    <ScrollArea className="h-[200px] w-full p-4" ref={scrollRef}>
                        <div className="space-y-3">
                            {steps.map((step, idx) => (
                                <div key={idx} className="flex gap-3 text-sm">
                                    <div className="min-w-[20px] pt-0.5">
                                        <Brain className="h-3.5 w-3.5 text-indigo-500/70" />
                                    </div>
                                    <div className="flex-1 space-y-1">
                                        <p className="text-indigo-100/90 leading-relaxed font-mono text-xs">
                                            {step.text}
                                        </p>
                                        {step.from_cache && (
                                            <span className="text-[10px] text-green-500/70 italic flex items-center gap-1">
                                                <Database className="h-2.5 w-2.5" /> Do cache
                                            </span>
                                        )}
                                    </div>
                                </div>
                            ))}

                            {status === 'running' && (
                                <div className="flex gap-2 items-center text-xs text-indigo-400/50 pl-8 animate-pulse">
                                    <span>Pensando...</span>
                                </div>
                            )}
                        </div>
                    </ScrollArea>
                </div>
            )}
        </Card>
    );
}
