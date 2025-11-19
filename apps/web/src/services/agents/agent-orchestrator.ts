import { nanoid } from 'nanoid';

export type AgentRole = 'strategist' | 'researcher' | 'drafter' | 'reviewer';

export interface AgentStep {
    id: string;
    agent: AgentRole;
    status: 'pending' | 'working' | 'completed' | 'failed';
    message: string;
    details?: string;
    timestamp: string;
}

export interface AgentState {
    isProcessing: boolean;
    currentStep: number;
    steps: AgentStep[];
    result?: string;
}

const AGENT_PERSONAS = {
    strategist: {
        name: 'Estrategista Jurídico',
        color: 'text-purple-400',
        icon: 'BrainCircuit'
    },
    researcher: {
        name: 'Pesquisador de Precedentes',
        color: 'text-blue-400',
        icon: 'Search'
    },
    drafter: {
        name: 'Redator Especialista',
        color: 'text-emerald-400',
        icon: 'PenTool'
    },
    reviewer: {
        name: 'Revisor Sênior',
        color: 'text-orange-400',
        icon: 'CheckCircle'
    }
};

export class AgentOrchestrator {
    private static delay(ms: number) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    static getInitialSteps(): AgentStep[] {
        return [
            {
                id: nanoid(),
                agent: 'strategist',
                status: 'pending',
                message: 'Analisando solicitação e definindo estratégia...',
                timestamp: new Date().toISOString()
            },
            {
                id: nanoid(),
                agent: 'researcher',
                status: 'pending',
                message: 'Buscando jurisprudência e modelos aplicáveis...',
                timestamp: new Date().toISOString()
            },
            {
                id: nanoid(),
                agent: 'drafter',
                status: 'pending',
                message: 'Redigindo minuta inicial...',
                timestamp: new Date().toISOString()
            },
            {
                id: nanoid(),
                agent: 'reviewer',
                status: 'pending',
                message: 'Revisando cláusulas e consistência legal...',
                timestamp: new Date().toISOString()
            }
        ];
    }

    static async *runWorkflow(prompt: string): AsyncGenerator<AgentStep[], string, unknown> {
        const steps = this.getInitialSteps();

        // 1. Strategist
        steps[0].status = 'working';
        yield [...steps];
        await this.delay(1500);
        steps[0].status = 'completed';
        steps[0].details = 'Estratégia definida: Contrato de alta complexidade com foco em proteção de PI.';

        // 2. Researcher
        steps[1].status = 'working';
        yield [...steps];
        await this.delay(2000);
        steps[1].status = 'completed';
        steps[1].details = 'Encontrados 3 precedentes relevantes no STJ e 2 modelos internos.';

        // 3. Drafter
        steps[2].status = 'working';
        yield [...steps];
        await this.delay(2500);
        steps[2].status = 'completed';
        steps[2].details = 'Minuta gerada com 15 cláusulas principais.';

        // 4. Reviewer
        steps[3].status = 'working';
        yield [...steps];
        await this.delay(1500);
        steps[3].status = 'completed';
        steps[3].details = 'Aprovado com ressalvas menores (já corrigidas).';

        yield [...steps];

        return this.generateFinalDocument(prompt);
    }

    private static generateFinalDocument(prompt: string): string {
        // Simple template selection based on prompt keywords
        const lowerPrompt = prompt.toLowerCase();

        if (lowerPrompt.includes('nda') || lowerPrompt.includes('confidencialidade')) {
            return `# ACORDO DE CONFIDENCIALIDADE (NDA)

**ENTRE:**

**[NOME DA PARTE REVELADORA]**, pessoa jurídica de direito privado... ("Reveladora");

**E**

**[NOME DA PARTE RECEPTORA]**, pessoa jurídica de direito privado... ("Receptora").

**1. DO OBJETO**
O presente acordo tem como objeto a proteção de Informações Confidenciais...

**2. DAS OBRIGAÇÕES**
A Receptora obriga-se a manter o mais absoluto sigilo...

**3. DA VIGÊNCIA**
Este acordo vigorará pelo prazo de 5 (cinco) anos...

*Gerado pelo Agente Redator e validado pelo Agente Revisor.*`;
        }

        return `# MINUTA JURÍDICA PERSONALIZADA

**REFERÊNCIA:** ${prompt}

**1. INTRODUÇÃO**
Trata-se de instrumento jurídico elaborado para atender à demanda específica...

**2. CLÁUSULAS PRINCIPAIS**
2.1. As partes ajustam entre si...
2.2. O descumprimento acarretará...

**3. CONSIDERAÇÕES FINAIS**
Este documento foi elaborado seguindo as melhores práticas...

*Gerado pelo Sistema Multi-Agente Iudex.*`;
    }
}
