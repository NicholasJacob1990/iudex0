/**
 * Agent Fallback via Claude API
 *
 * Quando seletores ARIA e CSS falham, usa Claude para analisar
 * screenshot + DOM e sugerir um seletor CSS válido.
 */

import type { Page } from 'playwright';
import type { AgentFallbackConfig, SemanticSelector } from '../types/index.js';

const DEFAULT_MODEL = 'claude-sonnet-4-20250514';
const DEFAULT_MAX_TOKENS = 1024;

interface AgentFallbackClient {
  askForSelector(
    page: Page,
    description: string,
    context: string,
    originalSelector: SemanticSelector,
  ): Promise<string | null>;
}

/**
 * Cria cliente de agent fallback.
 * Lazy-loads o SDK Anthropic para não impactar quem não usa.
 */
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
      originalSelector: SemanticSelector,
    ): Promise<string | null> {
      const client = await getClient();
      if (!client) return null;

      try {
        // 1. Captura screenshot (reduzido)
        const screenshotBuffer = await page.screenshot({
          fullPage: false,
          type: 'jpeg',
          quality: 60,
        });
        const screenshotBase64 = screenshotBuffer.toString('base64');

        // 2. Extrai DOM simplificado (só elementos interativos)
        const domSnapshot = await extractInteractiveDOM(page);

        // 3. Monta prompt
        const prompt = buildPrompt(description, context, originalSelector, domSnapshot);

        // 4. Chama Claude
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

        // 5. Extrai selector da resposta
        const text = response.content
          .filter((c: any) => c.type === 'text')
          .map((c: any) => c.text)
          .join('');

        const selector = extractSelectorFromResponse(text);
        if (!selector) return null;

        // 6. Valida se o selector funciona na página
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

// ============================================
// Helpers
// ============================================

/**
 * Extrai elementos interativos do DOM (inputs, buttons, links, selects).
 * Retorna HTML simplificado com no máximo 5000 caracteres.
 */
async function extractInteractiveDOM(page: Page): Promise<string> {
  return await page.evaluate(() => {
    const interactiveTags = ['INPUT', 'BUTTON', 'SELECT', 'TEXTAREA', 'A', 'LABEL'];
    const elements: string[] = [];

    function describeElement(el: Element): string {
      const tag = el.tagName.toLowerCase();
      const attrs: string[] = [];

      for (const attr of ['id', 'name', 'class', 'type', 'role', 'aria-label', 'placeholder', 'href', 'value']) {
        const val = el.getAttribute(attr);
        if (val) attrs.push(`${attr}="${val.substring(0, 80)}"`);
      }

      const text = el.textContent?.trim().substring(0, 60) ?? '';
      const textPart = text ? ` text="${text}"` : '';

      return `<${tag} ${attrs.join(' ')}${textPart}/>`;
    }

    for (const tag of interactiveTags) {
      const nodeList = document.querySelectorAll(tag);
      for (let i = 0; i < nodeList.length; i++) {
        const el = nodeList[i];
        if ((el as HTMLElement).offsetParent !== null) {
          elements.push(describeElement(el));
        }
      }
    }

    // Também inclui elementos com role explícito
    const roleNodes = document.querySelectorAll('[role]');
    for (let i = 0; i < roleNodes.length; i++) {
      const el = roleNodes[i];
      if ((el as HTMLElement).offsetParent !== null) {
        const desc = describeElement(el);
        if (!elements.includes(desc)) {
          elements.push(desc);
        }
      }
    }

    return elements.join('\n').substring(0, 5000);
  });
}

function buildPrompt(
  description: string,
  context: string,
  originalSelector: SemanticSelector,
  domSnapshot: string,
): string {
  return `Você é um assistente especializado em automação de navegador para sistemas judiciais brasileiros.

TAREFA: Encontre o elemento descrito abaixo na página e retorne APENAS um seletor CSS válido.

ELEMENTO PROCURADO: ${description}
CONTEXTO DA PÁGINA: ${context}
SELETOR ORIGINAL (que falhou):
- role: ${originalSelector.role}
- name: ${originalSelector.name instanceof RegExp ? originalSelector.name.source : originalSelector.name ?? 'N/A'}
- fallback CSS: ${originalSelector.fallback ?? 'N/A'}

ELEMENTOS INTERATIVOS NA PÁGINA:
${domSnapshot}

REGRAS:
1. Retorne APENAS o seletor CSS, sem explicação
2. O seletor deve ser específico o suficiente para ser único
3. Prefira seletores por ID > atributos > classe > hierarquia
4. O seletor deve funcionar com document.querySelector()
5. Formate a resposta assim: SELECTOR: <seu-seletor-aqui>

Analise o screenshot e o DOM para encontrar o elemento correto.`;
}

function extractSelectorFromResponse(text: string): string | null {
  // Tenta formato SELECTOR: ...
  const match = text.match(/SELECTOR:\s*(.+)/i);
  if (match) {
    return match[1].trim().replace(/^["'`]+|["'`]+$/g, '');
  }

  // Tenta extrair de code block
  const codeMatch = text.match(/```(?:css)?\s*\n?(.+?)\n?```/s);
  if (codeMatch) {
    return codeMatch[1].trim();
  }

  // Tenta a primeira linha que parece um seletor CSS
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
