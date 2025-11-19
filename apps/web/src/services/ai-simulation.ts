import { nanoid } from 'nanoid';

export interface SimulationResponse {
    content: string;
    isDone: boolean;
}

const LEGAL_TEMPLATES: Record<string, string> = {
    'nda': `# ACORDO DE CONFIDENCIALIDADE (NDA)

**ENTRE:**

**[NOME DA PARTE REVELADORA]**, pessoa jurídica de direito privado, inscrita no CNPJ sob o nº [CNPJ], com sede em [ENDEREÇO] ("Reveladora");

**E**

**[NOME DA PARTE RECEPTORA]**, pessoa jurídica de direito privado, inscrita no CNPJ sob o nº [CNPJ], com sede em [ENDEREÇO] ("Receptora").

**CONSIDERANDO QUE:**

A. A Reveladora possui certas informações confidenciais e proprietárias;
B. As Partes desejam discutir uma potencial relação comercial ("Propósito");

**ACORDAM O SEGUINTE:**

1. **DEFINIÇÃO DE INFORMAÇÃO CONFIDENCIAL**
   Para os fins deste Acordo, "Informação Confidencial" significa toda e qualquer informação técnica, comercial, financeira ou de outra natureza...

2. **OBRIGAÇÕES DE CONFIDENCIALIDADE**
   A Receptora concorda em manter o sigilo das Informações Confidenciais e não as utilizar para qualquer fim que não seja o Propósito...

3. **VIGÊNCIA**
   Este Acordo entra em vigor na data de sua assinatura e permanecerá válido por [PRAZO] anos.

[CIDADE], [DATA]

___________________________
[NOME DA REVELADORA]

___________________________
[NOME DA RECEPTORA]`,

    'procuracao': `# PROCURAÇÃO AD JUDICIA ET EXTRA JUDICIA

**OUTORGANTE:**
[NOME DO CLIENTE], [NACIONALIDADE], [ESTADO CIVIL], [PROFISSÃO], portador do RG nº [RG] e inscrito no CPF sob o nº [CPF], residente e domiciliado em [ENDEREÇO].

**OUTORGADO:**
[NOME DO ADVOGADO], advogado, inscrito na OAB/[UF] sob o nº [NÚMERO], com escritório profissional em [ENDEREÇO].

**PODERES:**
Pelo presente instrumento particular de procuração, o OUTORGANTE nomeia e constitui seu bastante procurador o OUTORGADO, conferindo-lhe amplos poderes para o foro em geral, com a cláusula "ad judicia et extra judicia", em qualquer Juízo, Instância ou Tribunal...

**PODERES ESPECÍFICOS:**
Conferem-se ainda poderes especiais para confessar, desistir, transigir, firmar compromissos ou acordos, receber e dar quitação, agindo em conjunto ou separadamente...

[CIDADE], [DATA]

___________________________
[ASSINATURA DO OUTORGANTE]`,

    'default': `Com base na sua solicitação, aqui está uma minuta preliminar.

# TÍTULO DO DOCUMENTO

**1. INTRODUÇÃO**
O presente documento tem por objetivo formalizar o entendimento entre as partes envolvidas...

**2. DO OBJETO**
O objeto deste instrumento é [DESCREVER OBJETO]...

**3. DAS OBRIGAÇÕES**
As partes comprometem-se a cumprir com todas as disposições legais aplicáveis...

*Esta é uma geração simulada para fins de demonstração. O Iudex está processando o contexto jurídico específico do seu caso para refinar esta minuta.*`
};

import { AgentOrchestrator, AgentStep } from './agents/agent-orchestrator';

export class AISimulationService {
    static async *streamAgentResponse(prompt: string): AsyncGenerator<AgentStep[], string, unknown> {
        const generator = AgentOrchestrator.runWorkflow(prompt);

        for await (const steps of generator) {
            yield steps;
        }

        // The return value of the generator is the final document
        // We need to handle this properly in the calling code
        return '';
    }

    static async generateChatResponse(prompt: string): Promise<string> {
        // Fallback for simple chat
        return "Estou iniciando o processo de geração multi-agente para sua solicitação. Por favor, acompanhe o progresso no painel lateral.";
    }
}
