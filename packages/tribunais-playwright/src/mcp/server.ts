#!/usr/bin/env node
/**
 * MCP Server para tribunais-playwright
 *
 * Fornece ferramentas para automação de tribunais via Model Context Protocol
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  type Tool,
} from '@modelcontextprotocol/sdk/types.js';
import { EprocClient } from '../eproc/client.js';
import type { AuthConfig, PeticaoOpcoes } from '../types/index.js';
import * as fs from 'fs/promises';
import * as path from 'path';

// ============================================
// Session Manager
// ============================================

interface Session {
  id: string;
  client: EprocClient;
  tribunal: string;
  status: 'ready' | 'logged_in' | 'error';
}

const sessions = new Map<string, Session>();
let sessionCounter = 0;

// ============================================
// Tools Definition
// ============================================

const tools: Tool[] = [
  // Session Management
  {
    name: 'tribunal_criar_sessao',
    description: 'Cria uma nova sessão do navegador para um tribunal. Retorna o ID da sessão.',
    inputSchema: {
      type: 'object',
      properties: {
        tribunal: {
          type: 'string',
          description: 'Código do tribunal (tjmg, trf4, tjrs)',
          enum: ['tjmg', 'trf4', 'tjrs'],
        },
        instancia: {
          type: 'string',
          description: 'Instância (1g ou 2g)',
          enum: ['1g', '2g'],
          default: '1g',
        },
        authType: {
          type: 'string',
          description: 'Tipo de autenticação',
          enum: ['password', 'certificate_a1', 'certificate_a3_physical', 'certificate_a3_cloud'],
        },
        headless: {
          type: 'boolean',
          description: 'Executar sem interface gráfica',
          default: false,
        },
      },
      required: ['tribunal', 'authType'],
    },
  },
  {
    name: 'tribunal_login',
    description: 'Faz login no tribunal. Para certificado A3, aguarda interação do usuário.',
    inputSchema: {
      type: 'object',
      properties: {
        sessionId: { type: 'string', description: 'ID da sessão' },
        cpf: { type: 'string', description: 'CPF (para login com senha)' },
        senha: { type: 'string', description: 'Senha (para login com senha)' },
        pfxPath: { type: 'string', description: 'Caminho do certificado .pfx (para A1)' },
        passphrase: { type: 'string', description: 'Senha do certificado (para A1)' },
        provider: {
          type: 'string',
          description: 'Provedor do certificado na nuvem',
          enum: ['certisign', 'serasa', 'safeweb', 'soluti'],
        },
      },
      required: ['sessionId'],
    },
  },
  {
    name: 'tribunal_logout',
    description: 'Faz logout do tribunal',
    inputSchema: {
      type: 'object',
      properties: {
        sessionId: { type: 'string', description: 'ID da sessão' },
      },
      required: ['sessionId'],
    },
  },
  {
    name: 'tribunal_fechar_sessao',
    description: 'Fecha a sessão e o navegador',
    inputSchema: {
      type: 'object',
      properties: {
        sessionId: { type: 'string', description: 'ID da sessão' },
      },
      required: ['sessionId'],
    },
  },

  // Window Control
  {
    name: 'tribunal_minimizar',
    description: 'Minimiza a janela do navegador',
    inputSchema: {
      type: 'object',
      properties: {
        sessionId: { type: 'string', description: 'ID da sessão' },
      },
      required: ['sessionId'],
    },
  },
  {
    name: 'tribunal_restaurar',
    description: 'Restaura a janela do navegador',
    inputSchema: {
      type: 'object',
      properties: {
        sessionId: { type: 'string', description: 'ID da sessão' },
      },
      required: ['sessionId'],
    },
  },

  // Process Operations
  {
    name: 'tribunal_consultar_processo',
    description: 'Consulta dados de um processo judicial',
    inputSchema: {
      type: 'object',
      properties: {
        sessionId: { type: 'string', description: 'ID da sessão' },
        numeroProcesso: { type: 'string', description: 'Número do processo (CNJ)' },
      },
      required: ['sessionId', 'numeroProcesso'],
    },
  },
  {
    name: 'tribunal_listar_documentos',
    description: 'Lista documentos de um processo',
    inputSchema: {
      type: 'object',
      properties: {
        sessionId: { type: 'string', description: 'ID da sessão' },
        numeroProcesso: { type: 'string', description: 'Número do processo' },
      },
      required: ['sessionId', 'numeroProcesso'],
    },
  },
  {
    name: 'tribunal_listar_movimentacoes',
    description: 'Lista movimentações/andamentos de um processo',
    inputSchema: {
      type: 'object',
      properties: {
        sessionId: { type: 'string', description: 'ID da sessão' },
        numeroProcesso: { type: 'string', description: 'Número do processo' },
      },
      required: ['sessionId', 'numeroProcesso'],
    },
  },
  {
    name: 'tribunal_baixar_processo',
    description: 'Baixa todos os documentos de um processo para uma pasta local',
    inputSchema: {
      type: 'object',
      properties: {
        sessionId: { type: 'string', description: 'ID da sessão' },
        numeroProcesso: { type: 'string', description: 'Número do processo' },
        destino: { type: 'string', description: 'Pasta de destino para os arquivos' },
      },
      required: ['sessionId', 'numeroProcesso', 'destino'],
    },
  },

  // Petitioning
  {
    name: 'tribunal_peticionar',
    description: 'Protocola uma petição em um processo',
    inputSchema: {
      type: 'object',
      properties: {
        sessionId: { type: 'string', description: 'ID da sessão' },
        numeroProcesso: { type: 'string', description: 'Número do processo' },
        tipo: { type: 'string', description: 'Tipo da petição' },
        descricao: { type: 'string', description: 'Descrição/assunto' },
        arquivos: {
          type: 'array',
          items: { type: 'string' },
          description: 'Caminhos dos arquivos PDF para anexar',
        },
        tiposDocumento: {
          type: 'array',
          items: { type: 'string' },
          description: 'Tipos de cada documento',
        },
      },
      required: ['sessionId', 'numeroProcesso', 'tipo', 'arquivos'],
    },
  },

  // Utilities
  {
    name: 'tribunal_screenshot',
    description: 'Captura screenshot da tela atual',
    inputSchema: {
      type: 'object',
      properties: {
        sessionId: { type: 'string', description: 'ID da sessão' },
        destino: { type: 'string', description: 'Caminho para salvar a imagem' },
      },
      required: ['sessionId'],
    },
  },
  {
    name: 'tribunal_listar_sessoes',
    description: 'Lista todas as sessões ativas',
    inputSchema: {
      type: 'object',
      properties: {},
    },
  },
];

// ============================================
// Tool Handlers
// ============================================

function getBaseUrl(tribunal: string, instancia: string): string {
  const urls: Record<string, Record<string, string>> = {
    tjmg: {
      '1g': 'https://eproc1g.tjmg.jus.br/eproc/',
      '2g': 'https://eproc2g.tjmg.jus.br/eproc/',
    },
    trf4: {
      '1g': 'https://eproc.trf4.jus.br/eproc2trf4',
      '2g': 'https://eproc.trf4.jus.br/eproc2trf4',
    },
    tjrs: {
      '1g': 'https://eproc1g.tjrs.jus.br/eproc/',
      '2g': 'https://eproc2g.tjrs.jus.br/eproc/',
    },
  };
  return urls[tribunal]?.[instancia] ?? urls[tribunal]?.['1g'] ?? '';
}

async function handleTool(name: string, args: Record<string, unknown>): Promise<string> {
  switch (name) {
    // ==========================================
    // Session Management
    // ==========================================
    case 'tribunal_criar_sessao': {
      const tribunal = args.tribunal as string;
      const instancia = (args.instancia as string) ?? '1g';
      const authType = args.authType as string;
      const headless = (args.headless as boolean) ?? false;

      const baseUrl = getBaseUrl(tribunal, instancia);
      if (!baseUrl) {
        return JSON.stringify({ error: `Tribunal não suportado: ${tribunal}` });
      }

      // Build auth config placeholder
      let auth: AuthConfig;
      switch (authType) {
        case 'password':
          auth = { type: 'password', cpf: '', senha: '' };
          break;
        case 'certificate_a1':
          auth = { type: 'certificate_a1', pfxPath: '', passphrase: '' };
          break;
        case 'certificate_a3_physical':
          auth = { type: 'certificate_a3_physical' };
          break;
        case 'certificate_a3_cloud':
          auth = { type: 'certificate_a3_cloud', provider: 'certisign' };
          break;
        default:
          return JSON.stringify({ error: `Tipo de auth não suportado: ${authType}` });
      }

      const sessionId = `session_${++sessionCounter}`;
      const client = new EprocClient({
        baseUrl,
        auth,
        tribunal,
        instancia: instancia as '1g' | '2g',
        playwright: {
          headless,
          persistent: true,
          keepAlive: true,
          timeout: 60000,
        },
      });

      await client.init();

      sessions.set(sessionId, {
        id: sessionId,
        client,
        tribunal,
        status: 'ready',
      });

      return JSON.stringify({
        sessionId,
        tribunal,
        instancia,
        authType,
        status: 'ready',
        message: 'Sessão criada. Use tribunal_login para autenticar.',
      });
    }

    case 'tribunal_login': {
      const sessionId = args.sessionId as string;
      const session = sessions.get(sessionId);
      if (!session) {
        return JSON.stringify({ error: `Sessão não encontrada: ${sessionId}` });
      }

      // Update auth config based on provided credentials
      const config = (session.client as any).config;

      if (args.cpf && args.senha) {
        config.auth = { type: 'password', cpf: args.cpf, senha: args.senha };
      } else if (args.pfxPath && args.passphrase) {
        config.auth = {
          type: 'certificate_a1',
          pfxPath: args.pfxPath,
          passphrase: args.passphrase,
        };
      } else if (args.provider) {
        config.auth = {
          type: 'certificate_a3_cloud',
          provider: args.provider,
          approvalTimeout: 120000,
        };
      }

      try {
        const success = await session.client.login();
        if (success) {
          session.status = 'logged_in';
          return JSON.stringify({
            success: true,
            message: 'Login realizado com sucesso',
            currentUrl: session.client.getCurrentUrl(),
          });
        } else {
          return JSON.stringify({ success: false, error: 'Login falhou' });
        }
      } catch (err) {
        return JSON.stringify({
          success: false,
          error: err instanceof Error ? err.message : String(err),
        });
      }
    }

    case 'tribunal_logout': {
      const session = sessions.get(args.sessionId as string);
      if (!session) {
        return JSON.stringify({ error: 'Sessão não encontrada' });
      }
      await session.client.logout();
      session.status = 'ready';
      return JSON.stringify({ success: true, message: 'Logout realizado' });
    }

    case 'tribunal_fechar_sessao': {
      const sessionId = args.sessionId as string;
      const session = sessions.get(sessionId);
      if (!session) {
        return JSON.stringify({ error: 'Sessão não encontrada' });
      }
      await session.client.close();
      sessions.delete(sessionId);
      return JSON.stringify({ success: true, message: 'Sessão fechada' });
    }

    // ==========================================
    // Window Control
    // ==========================================
    case 'tribunal_minimizar': {
      const session = sessions.get(args.sessionId as string);
      if (!session) {
        return JSON.stringify({ error: 'Sessão não encontrada' });
      }
      await session.client.minimizeWindow();
      return JSON.stringify({ success: true, message: 'Janela minimizada' });
    }

    case 'tribunal_restaurar': {
      const session = sessions.get(args.sessionId as string);
      if (!session) {
        return JSON.stringify({ error: 'Sessão não encontrada' });
      }
      await session.client.restoreWindow();
      return JSON.stringify({ success: true, message: 'Janela restaurada' });
    }

    // ==========================================
    // Process Operations
    // ==========================================
    case 'tribunal_consultar_processo': {
      const session = sessions.get(args.sessionId as string);
      if (!session) {
        return JSON.stringify({ error: 'Sessão não encontrada' });
      }
      if (session.status !== 'logged_in') {
        return JSON.stringify({ error: 'Faça login primeiro' });
      }

      const processo = await session.client.consultarProcesso(args.numeroProcesso as string);
      return JSON.stringify(processo ?? { error: 'Processo não encontrado' });
    }

    case 'tribunal_listar_documentos': {
      const session = sessions.get(args.sessionId as string);
      if (!session) {
        return JSON.stringify({ error: 'Sessão não encontrada' });
      }
      if (session.status !== 'logged_in') {
        return JSON.stringify({ error: 'Faça login primeiro' });
      }

      const docs = await session.client.listarDocumentos(args.numeroProcesso as string);
      return JSON.stringify({ documentos: docs, total: docs.length });
    }

    case 'tribunal_listar_movimentacoes': {
      const session = sessions.get(args.sessionId as string);
      if (!session) {
        return JSON.stringify({ error: 'Sessão não encontrada' });
      }
      if (session.status !== 'logged_in') {
        return JSON.stringify({ error: 'Faça login primeiro' });
      }

      const movs = await session.client.listarMovimentacoes(args.numeroProcesso as string);
      return JSON.stringify({ movimentacoes: movs, total: movs.length });
    }

    case 'tribunal_baixar_processo': {
      const session = sessions.get(args.sessionId as string);
      if (!session) {
        return JSON.stringify({ error: 'Sessão não encontrada' });
      }
      if (session.status !== 'logged_in') {
        return JSON.stringify({ error: 'Faça login primeiro' });
      }

      const numeroProcesso = args.numeroProcesso as string;
      const destino = args.destino as string;

      // Create destination folder
      await fs.mkdir(destino, { recursive: true });

      // Get process info
      const processo = await session.client.consultarProcesso(numeroProcesso);
      if (!processo) {
        return JSON.stringify({ error: 'Processo não encontrado' });
      }

      // Save process metadata
      await fs.writeFile(
        path.join(destino, 'processo.json'),
        JSON.stringify(processo, null, 2)
      );

      // Get documents
      const docs = await session.client.listarDocumentos(numeroProcesso);

      // Get movements
      const movs = await session.client.listarMovimentacoes(numeroProcesso);
      await fs.writeFile(
        path.join(destino, 'movimentacoes.json'),
        JSON.stringify(movs, null, 2)
      );

      // Note: Actual document download would require implementation
      // in the EprocClient. For now, we save the list.
      await fs.writeFile(
        path.join(destino, 'documentos.json'),
        JSON.stringify(docs, null, 2)
      );

      return JSON.stringify({
        success: true,
        destino,
        processo: processo.numero,
        documentos: docs.length,
        movimentacoes: movs.length,
        arquivos: ['processo.json', 'documentos.json', 'movimentacoes.json'],
        message: 'Metadados do processo baixados. Download de PDFs requer implementação adicional.',
      });
    }

    // ==========================================
    // Petitioning
    // ==========================================
    case 'tribunal_peticionar': {
      const session = sessions.get(args.sessionId as string);
      if (!session) {
        return JSON.stringify({ error: 'Sessão não encontrada' });
      }
      if (session.status !== 'logged_in') {
        return JSON.stringify({ error: 'Faça login primeiro' });
      }

      const opcoes: PeticaoOpcoes = {
        numeroProcesso: args.numeroProcesso as string,
        tipo: args.tipo as string,
        descricao: args.descricao as string | undefined,
        arquivos: args.arquivos as string[],
        tiposDocumento: args.tiposDocumento as string[] | undefined,
      };

      const resultado = await session.client.peticionar(opcoes);
      return JSON.stringify(resultado);
    }

    // ==========================================
    // Utilities
    // ==========================================
    case 'tribunal_screenshot': {
      const session = sessions.get(args.sessionId as string);
      if (!session) {
        return JSON.stringify({ error: 'Sessão não encontrada' });
      }

      const destino = (args.destino as string) ?? `/tmp/tribunal_${Date.now()}.png`;
      await session.client.screenshot(destino);
      return JSON.stringify({ success: true, path: destino });
    }

    case 'tribunal_listar_sessoes': {
      const list = Array.from(sessions.values()).map((s) => ({
        id: s.id,
        tribunal: s.tribunal,
        status: s.status,
      }));
      return JSON.stringify({ sessoes: list, total: list.length });
    }

    default:
      return JSON.stringify({ error: `Ferramenta desconhecida: ${name}` });
  }
}

// ============================================
// MCP Server
// ============================================

async function main() {
  const server = new Server(
    {
      name: 'tribunais-mcp',
      version: '0.1.0',
    },
    {
      capabilities: {
        tools: {},
      },
    }
  );

  // List tools
  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools,
  }));

  // Call tool
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;

    try {
      const result = await handleTool(name, args ?? {});
      return {
        content: [{ type: 'text', text: result }],
      };
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      return {
        content: [{ type: 'text', text: JSON.stringify({ error: errorMsg }) }],
        isError: true,
      };
    }
  });

  // Start server
  const transport = new StdioServerTransport();
  await server.connect(transport);

  console.error('[tribunais-mcp] Servidor MCP iniciado');
}

main().catch((err) => {
  console.error('[tribunais-mcp] Erro fatal:', err);
  process.exit(1);
});
