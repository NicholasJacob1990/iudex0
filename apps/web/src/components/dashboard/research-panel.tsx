import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';

export interface ResearchPanelData {
    planner: any;
    research: {
        latest: any[];
        steps: string[];
    };
    ragDecisions: Array<{
        section: string;
        routing?: any;
        gate?: any;
    }>;
}

const listValue = (items: string[] = []) => {
    if (!items.length) return '-';
    return items.slice(0, 5).join(', ');
};

export function ResearchPanel({ data }: { data: ResearchPanelData }) {
    const planner = data?.planner || {};
    const plannedQueries = Array.isArray(planner?.plannedqueries) ? planner.plannedqueries : [];

    return (
        <div className="rounded-2xl border border-outline/20 bg-white p-4">
            <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase text-muted-foreground">Pesquisa</h3>
                <Badge variant="outline" className="text-[10px]">Compacto</Badge>
            </div>
            <Accordion type="single" collapsible className="mt-2">
                <AccordionItem value="planner">
                    <AccordionTrigger className="text-xs">Planner</AccordionTrigger>
                    <AccordionContent className="text-[11px] text-muted-foreground space-y-2">
                        <div>Modo: <span className="text-foreground/80">{planner?.researchmode || '-'}</span></div>
                        <div>Need juris: <span className="text-foreground/80">{String(planner?.needjuris ?? '-')}</span></div>
                        <div>Queries: <span className="text-foreground/80">{listValue(plannedQueries)}</span></div>
                        {planner?.planningreasoning && (
                            <div className="text-foreground/80">{planner.planningreasoning}</div>
                        )}
                    </AccordionContent>
                </AccordionItem>

                <AccordionItem value="research">
                    <AccordionTrigger className="text-xs">Deep/Web Research</AccordionTrigger>
                    <AccordionContent className="text-[11px] text-muted-foreground space-y-3">
                        {data?.research?.latest?.length ? (
                            data.research.latest.map((item, idx) => (
                                <div key={`research-${idx}`}>
                                    <div className="text-foreground/80">
                                        {item?.data?.researchmode || item?.researchmode || '-'}: {item?.data?.sources_count ?? item?.sources_count ?? '0'} fontes
                                    </div>
                                </div>
                            ))
                        ) : (
                            <div>Sem resultados de pesquisa ainda.</div>
                        )}

                        {data?.research?.steps?.length > 0 && (
                            <div className="space-y-1">
                                <div className="text-[10px] uppercase text-muted-foreground">Passos (resumo)</div>
                                <ul className="list-disc pl-4 space-y-1">
                                    {data.research.steps.map((step, idx) => (
                                        <li key={`step-${idx}`}>{step}</li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </AccordionContent>
                </AccordionItem>

                <AccordionItem value="rag">
                    <AccordionTrigger className="text-xs">Decisoes de RAG</AccordionTrigger>
                    <AccordionContent className="text-[11px] text-muted-foreground space-y-3">
                        {data?.ragDecisions?.length ? (
                            data.ragDecisions.slice(0, 6).map((item) => (
                                <div key={item.section} className="space-y-1">
                                    <div className="text-foreground/80 font-semibold">{item.section}</div>
                                    <div>Strategy: {item.routing?.strategy || '-'}</div>
                                    <div>Sources: {listValue(item.routing?.sources || [])}</div>
                                    <div>TopK: {item.routing?.topk || '-'}</div>
                                    {item.gate && (
                                        <div>
                                            Gate: {item.gate.gatepassed ? 'passou' : 'falhou'} | Safe: {String(item.gate.safemode)}
                                        </div>
                                    )}
                                </div>
                            ))
                        ) : (
                            <div>Nenhuma decisao de RAG registrada.</div>
                        )}
                    </AccordionContent>
                </AccordionItem>
            </Accordion>
        </div>
    );
}
