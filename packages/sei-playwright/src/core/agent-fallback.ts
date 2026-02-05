/**
 * Agent Fallback via Claude API para SEI
 */

import type { Page } from 'playwright';
import type { AgentFallbackConfig } from '../types.js';

const DEFAULT_MODEL = 'claude-sonnet-4-20250514';
const DEFAULT_MAX_TOKENS = 1024;

/** Tipo semântico simplificado para seletores SEI */
export interface SelectorDescription {
  role: string;
  name: string | RegExp;
  cssFallback?: string;
}

export interface AgentFallbackClient {
  askForSelector(
    page: Page,
    description: string,
    context: string,
    original: SelectorDescription,
  ): Promise<string | null>;
}

export function createAgentFallback(config: AgentFallbackConfig): AgentFallbackClient | null {
  if (!config.enabled) return null;

  const apiKey = config.apiKey ?? process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    console.warn('[AGENT-FALLBACK] Nenhuma API key encontrada. Desativando agent fallback.');
    return null;
  }

  let anthropicClient: any = null;

  async function getClient(): Promise<any> {
    if (anthropicClient) return anthropicClient;

    try {
      const { default: Anthropic } = await import('@anthropic-ai/sdk');
      anthropicClient = new Anthropic({ apiKey });
      return anthropicClient;
    } catch {
      console.warn('[AGENT-FALLBACK] @anthropic-ai/sdk não instalado. Desativando agent fallback.');
      return null;
    }
  }

  return {
    async askForSelector(
      page: Page,
      description: string,
      context: string,
      original: SelectorDescription,
    ): Promise<string | null> {
      const client = await getClient();
      if (!client) return null;

      try {
        const screenshotBuffer = await page.screenshot({
          fullPage: false,
          type: 'jpeg',
          quality: 60,
        });
        const screenshotBase64 = screenshotBuffer.toString('base64');

        const domSnapshot = await extractInteractiveDOM(page);

        const nameStr = original.name instanceof RegExp ? original.name.source : original.name;
        const prompt = `Você é um assistente especializado em automação do sistema SEI (Sistema Eletrônico de Informações) do governo brasileiro.

TAREFA: Encontre o elemento descrito abaixo na página e retorne APENAS um seletor CSS válido.

ELEMENTO PROCURADO: ${description}
CONTEXTO DA PÁGINA: ${context}
SELETOR ORIGINAL (que falhou):
- role: ${original.role}
- name: ${nameStr}
- fallback CSS: ${original.cssFallback ?? 'N/A'}

ELEMENTOS INTERATIVOS NA PÁGINA:
${domSnapshot}

REGRAS:
1. Retorne APENAS o seletor CSS, sem explicação
2. O seletor deve ser específico o suficiente para ser único
3. Prefira seletores por ID > atributos > classe > hierarquia
4. O seletor deve funcionar com document.querySelector()
5. Formate a resposta assim: SELECTOR: <seu-seletor-aqui>

Analise o screenshot e o DOM para encontrar o elemento correto.`;

        const response = await client.messages.create({
          model: config.model ?? DEFAULT_MODEL,
          max_tokens: config.maxTokens ?? DEFAULT_MAX_TOKENS,
          messages: [
            {
              role: 'user',
              content: [
                {
                  type: 'image',
                  source: {
                    type: 'base64',
                    media_type: 'image/jpeg',
                    data: screenshotBase64,
                  },
                },
                {
                  type: 'text',
                  text: prompt,
                },
              ],
            },
          ],
        });

        const text = response.content
          .filter((c: any) => c.type === 'text')
          .map((c: any) => c.text)
          .join('');

        const selector = extractSelectorFromResponse(text);
        if (!selector) return null;

        const valid = await validateSelector(page, selector);
        if (!valid) return null;

        return selector;
      } catch (error) {
        console.warn('[AGENT-FALLBACK] Erro ao consultar agent:', error);
        return null;
      }
    },
  };
}

async function extractInteractiveDOM(page: Page): Promise<string> {
  // Código roda no contexto do browser via page.evaluate
  // Tipos DOM não disponíveis no tsconfig do Node — usa any
  return await page.evaluate((): string => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const doc = (globalThis as any).document;
    const interactiveTags = ['INPUT', 'BUTTON', 'SELECT', 'TEXTAREA', 'A', 'LABEL'];
    const elements: string[] = [];

    function describeElement(el: any): string {
      const tag = (el.tagName as string).toLowerCase();
      const attrs: string[] = [];

      for (const attr of ['id', 'name', 'class', 'type', 'role', 'aria-label', 'placeholder', 'href', 'value']) {
        const val = el.getAttribute(attr);
        if (val) attrs.push(`${attr}="${(val as string).substring(0, 80)}"`);
      }

      const text = ((el.textContent as string) ?? '').trim().substring(0, 60);
      const textPart = text ? ` text="${text}"` : '';

      return `<${tag} ${attrs.join(' ')}${textPart}/>`;
    }

    for (const tag of interactiveTags) {
      const nodeList = doc.querySelectorAll(tag);
      for (let i = 0; i < nodeList.length; i++) {
        const el = nodeList[i];
        if (el.offsetParent !== null) {
          elements.push(describeElement(el));
        }
      }
    }

    const roleNodes = doc.querySelectorAll('[role]');
    for (let i = 0; i < roleNodes.length; i++) {
      const el = roleNodes[i];
      if (el.offsetParent !== null) {
        const desc = describeElement(el);
        if (!elements.includes(desc)) {
          elements.push(desc);
        }
      }
    }

    return elements.join('\n').substring(0, 5000);
  });
}

function extractSelectorFromResponse(text: string): string | null {
  const match = text.match(/SELECTOR:\s*(.+)/i);
  if (match) {
    return match[1].trim().replace(/^["'`]+|["'`]+$/g, '');
  }

  const codeMatch = text.match(/```(?:css)?\s*\n?(.+?)\n?```/s);
  if (codeMatch) {
    return codeMatch[1].trim();
  }

  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
  for (const line of lines) {
    if (/^[#.\[\w]/.test(line) && !line.includes(' ') || line.includes('[') || line.startsWith('#')) {
      return line;
    }
  }

  return null;
}

async function validateSelector(page: Page, selector: string): Promise<boolean> {
  try {
    const el = await page.$(selector);
    return el !== null;
  } catch {
    return false;
  }
}
