/**
 * Serviço de operações em tribunais
 *
 * Executa operações usando tribunais-playwright:
 * - Consultas de processo
 * - Listagem de documentos/movimentações
 * - Download de documentos
 * - Peticionamento
 */

import {
  EprocClient,
  PJeClient,
  // ESAJClient, // TODO: implementar
  type TribunalClientConfig,
  type AuthConfig,
} from 'tribunais-playwright';
import { writeFileSync, unlinkSync, mkdtempSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import type {
  DecryptedCredential,
  TribunalType,
  OperationType,
  OperationResult,
  ProcessoInfo,
  DocumentoInfo,
  MovimentacaoInfo,
  PetitionFile,
  PetitionResult,
  CaptchaInfo,
  CaptchaSolution,
} from '../types/index.js';
import { logger } from '../utils/logger.js';

// Opções para execução de operação
export interface ExecuteOperationOptions {
  /**
   * Callback chamado quando CAPTCHA é detectado.
   * Deve resolver o CAPTCHA e retornar a solução.
   */
  onCaptchaRequired?: (captcha: CaptchaInfo) => Promise<CaptchaSolution>;
}

// Tipo genérico para clientes de tribunal
type TribunalClient = EprocClient | PJeClient;

export class TribunalService {
  private activeClients = new Map<string, TribunalClient>();
  private tempFiles: string[] = []; // Track temp files for cleanup

  /**
   * Cria cliente de tribunal baseado no tipo
   */
  private createClient(
    tribunal: TribunalType,
    tribunalUrl: string,
    auth: AuthConfig,
    options?: Partial<TribunalClientConfig>
  ): TribunalClient {
    const clientOptions: TribunalClientConfig = {
      baseUrl: tribunalUrl,
      auth,
      playwright: {
        headless: true,
        timeout: 60000,
        ...options?.playwright,
      },
      ...options,
    };

    switch (tribunal) {
      case 'eproc':
        return new EprocClient(clientOptions);
      case 'pje':
        return new PJeClient(clientOptions);
      case 'esaj':
        // TODO: Implementar ESAJClient
        throw new Error('e-SAJ ainda não implementado');
      default:
        throw new Error(`Tribunal não suportado: ${tribunal}`);
    }
  }

  /**
   * Converte credencial descriptografada para AuthConfig
   */
  private getAuthConfig(credential: DecryptedCredential): AuthConfig {
    switch (credential.authType) {
      case 'password':
        return {
          type: 'password',
          cpf: credential.cpf!,
          senha: credential.password!,
        };

      case 'certificate_a1': {
        // Save pfxBuffer to temp file (tribunais-playwright expects file path)
        const tempDir = mkdtempSync(join(tmpdir(), 'tribunais-'));
        const pfxPath = join(tempDir, 'certificate.pfx');
        writeFileSync(pfxPath, credential.pfxBuffer!);
        this.tempFiles.push(pfxPath);

        return {
          type: 'certificate_a1',
          pfxPath,
          passphrase: credential.pfxPassword!,
        };
      }

      case 'certificate_a3_cloud':
        return {
          type: 'certificate_a3_cloud',
          provider: credential.cloudProvider!,
        };

      case 'certificate_a3_physical':
        return {
          type: 'certificate_a3_physical',
        };

      default:
        throw new Error(`Tipo de autenticação não suportado: ${credential.authType}`);
    }
  }

  /**
   * Limpa arquivos temporários
   */
  private cleanupTempFiles(): void {
    for (const file of this.tempFiles) {
      try {
        unlinkSync(file);
      } catch {
        // Ignore cleanup errors
      }
    }
    this.tempFiles = [];
  }

  /**
   * Executa operação genérica em tribunal
   */
  async executeOperation(
    credential: DecryptedCredential,
    operation: OperationType,
    params: Record<string, unknown>,
    options?: ExecuteOperationOptions
  ): Promise<OperationResult> {
    const startTime = Date.now();
    let client: TribunalClient | null = null;

    try {
      // Criar cliente
      const auth = this.getAuthConfig(credential);

      // Configurar CAPTCHA callback se fornecido
      const clientOptions: Partial<TribunalClientConfig> = {};
      if (options?.onCaptchaRequired) {
        clientOptions.captcha = {
          mode: 'manual',
          onCaptchaRequired: async (captchaInfo) => {
            // Converter formato tribunais-playwright para nosso formato
            const captcha: CaptchaInfo = {
              type: captchaInfo.type as CaptchaInfo['type'],
              siteKey: captchaInfo.siteKey,
              imageBase64: captchaInfo.imageBase64,
              // pageUrl e outros campos podem ser usados como metadata
              metadata: { pageUrl: captchaInfo.pageUrl },
            };

            const solution = await options.onCaptchaRequired!(captcha);

            // Retornar token ou texto conforme esperado pelo tribunais-playwright
            return solution.token || solution.text || '';
          },
        };
      }

      client = this.createClient(credential.tribunal, credential.tribunalUrl, auth, clientOptions);

      // Inicializar e fazer login
      await client.init();
      await client.login();

      // Executar operação específica
      let data: unknown;

      switch (operation) {
        case 'consultar_processo':
          data = await this.consultarProcesso(client, params.processo as string);
          break;

        case 'listar_documentos':
          data = await this.listarDocumentos(client, params.processo as string);
          break;

        case 'listar_movimentacoes':
          data = await this.listarMovimentacoes(client, params.processo as string);
          break;

        case 'baixar_documento':
          data = await this.baixarDocumento(
            client,
            params.processo as string,
            params.documentoId as string
          );
          break;

        case 'baixar_processo':
          data = await this.baixarProcesso(client, params.processo as string);
          break;

        case 'peticionar':
          data = await this.peticionar(
            client,
            params.processo as string,
            params.tipo as string,
            params.arquivos as PetitionFile[]
          );
          break;

        default:
          throw new Error(`Operação não suportada: ${operation}`);
      }

      logger.info(`Operação ${operation} concluída em ${Date.now() - startTime}ms`);

      return {
        success: true,
        operation,
        data,
        executedAt: new Date(),
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro desconhecido';
      logger.error(`Erro na operação ${operation}:`, error);

      return {
        success: false,
        operation,
        error: message,
        executedAt: new Date(),
      };
    } finally {
      // Fechar cliente
      if (client) {
        try {
          await client.close();
        } catch {
          // Ignorar erros ao fechar
        }
      }

      // Limpar arquivos temporários
      this.cleanupTempFiles();
    }
  }

  /**
   * Consulta dados do processo
   */
  private async consultarProcesso(
    client: TribunalClient,
    processo: string
  ): Promise<ProcessoInfo> {
    const dados = await client.consultarProcesso(processo);

    if (!dados) {
      throw new Error(`Processo ${processo} não encontrado`);
    }

    // Map partes from tribunais-playwright format to Iudex format
    const partes = dados.partes?.map((p) => ({
      polo: p.tipo === 'autor' ? 'ativo' as const : 'passivo' as const,
      nome: p.nome,
      documento: p.documento,
      advogados: p.advogados?.map((a) => `${a.nome} (OAB/${a.uf} ${a.oab})`),
    }));

    return {
      numero: dados.numero,
      classe: dados.classe,
      assunto: dados.assunto,
      dataDistribuicao: dados.dataDistribuicao ? new Date(dados.dataDistribuicao) : undefined,
      valorCausa: dados.valorCausa,
      partes,
      situacao: dados.status,
    };
  }

  /**
   * Lista documentos do processo
   */
  private async listarDocumentos(
    client: TribunalClient,
    processo: string
  ): Promise<DocumentoInfo[]> {
    const documentos = await client.listarDocumentos(processo);

    return documentos.map((doc) => ({
      id: doc.id,
      tipo: doc.tipo,
      descricao: doc.nome,
      dataJuntada: doc.data ? new Date(doc.data) : new Date(),
      assinado: doc.assinado,
      signatarios: doc.signatarios,
    }));
  }

  /**
   * Lista movimentações do processo
   */
  private async listarMovimentacoes(
    client: TribunalClient,
    processo: string
  ): Promise<MovimentacaoInfo[]> {
    const movimentacoes = await client.listarMovimentacoes(processo);

    return movimentacoes.map((mov, index) => ({
      id: String(index),
      data: mov.data ? new Date(mov.data) : new Date(),
      tipo: mov.tipo ?? 'movimentacao',
      descricao: mov.descricao,
    }));
  }

  /**
   * Baixa documento específico
   */
  private async baixarDocumento(
    client: TribunalClient,
    processo: string,
    documentoId: string
  ): Promise<{ buffer: Buffer; filename: string; mimeType: string }> {
    // TODO: Implementar no cliente base
    throw new Error('baixarDocumento ainda não implementado');
  }

  /**
   * Baixa processo completo (metadados)
   */
  private async baixarProcesso(
    client: TribunalClient,
    processo: string
  ): Promise<ProcessoInfo & { documentos: DocumentoInfo[]; movimentacoes: MovimentacaoInfo[] }> {
    const [dados, documentos, movimentacoes] = await Promise.all([
      this.consultarProcesso(client, processo),
      this.listarDocumentos(client, processo),
      this.listarMovimentacoes(client, processo),
    ]);

    return {
      ...dados,
      documentos,
      movimentacoes,
    };
  }

  /**
   * Protocola petição
   */
  private async peticionar(
    client: TribunalClient,
    processo: string,
    tipo: string,
    arquivos: PetitionFile[]
  ): Promise<PetitionResult> {
    // Preparar arquivos para envio
    // tribunais-playwright expects file paths, so we need to save base64 files to temp
    const tempDir = mkdtempSync(join(tmpdir(), 'petition-'));
    const arquivoPaths: string[] = [];
    const tiposDocumento: string[] = [];

    for (const arq of arquivos) {
      let filePath: string;

      if (arq.path) {
        // Use existing path
        filePath = arq.path;
      } else if (arq.base64) {
        // Save base64 to temp file
        filePath = join(tempDir, arq.name);
        const buffer = Buffer.from(arq.base64, 'base64');
        writeFileSync(filePath, buffer);
        this.tempFiles.push(filePath);
      } else {
        throw new Error(`Arquivo ${arq.name} sem path ou base64`);
      }

      arquivoPaths.push(filePath);
      tiposDocumento.push(arq.tipoDocumento || 'Petição');
    }

    // Peticionar
    const resultado = await client.peticionar({
      numeroProcesso: processo,
      tipo,
      arquivos: arquivoPaths,
      tiposDocumento,
    });

    return {
      success: resultado.success,
      protocolo: resultado.numeroProtocolo,
      dataProtocolo: resultado.dataProtocolo ? new Date(resultado.dataProtocolo) : undefined,
      error: resultado.error,
      details: { mensagem: resultado.mensagem },
    };
  }

  /**
   * Verifica se precisa de interação do usuário (A3)
   */
  needsUserInteraction(authType: string): boolean {
    return authType === 'certificate_a3_physical' || authType === 'certificate_a3_cloud';
  }
}
