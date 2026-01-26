/**
 * Gerenciador de Certificados Digitais
 *
 * Detecta e usa certificados instalados no sistema:
 * - Tokens USB (A3 físico)
 * - Certificados do sistema operacional
 *
 * No macOS: Keychain
 * No Windows: Certificate Store
 * No Linux: PKCS#11 / OpenSC
 */

import { execSync, spawn } from 'child_process';
import { platform } from 'os';

export interface CertificateInfo {
  id: string;
  name: string;
  subject: string;
  issuer: string;
  serialNumber: string;
  validFrom: Date;
  validTo: Date;
  isExpired: boolean;
  hasPrivateKey: boolean;
  provider: 'system' | 'token' | 'file';
}

export class CertificateManager {
  private platform = platform();

  /**
   * Lista certificados disponíveis no sistema
   */
  async listCertificates(): Promise<CertificateInfo[]> {
    switch (this.platform) {
      case 'darwin':
        return this.listMacOSCertificates();
      case 'win32':
        return this.listWindowsCertificates();
      case 'linux':
        return this.listLinuxCertificates();
      default:
        return [];
    }
  }

  /**
   * Obtém informações detalhadas de um certificado
   */
  async getCertificateInfo(certId: string): Promise<CertificateInfo | null> {
    const certs = await this.listCertificates();
    return certs.find((c) => c.id === certId) || null;
  }

  /**
   * Assina dados com o certificado especificado
   */
  async sign(certId: string, pin: string, data: Buffer): Promise<Buffer> {
    switch (this.platform) {
      case 'darwin':
        return this.signMacOS(certId, pin, data);
      case 'win32':
        return this.signWindows(certId, pin, data);
      case 'linux':
        return this.signLinux(certId, pin, data);
      default:
        throw new Error(`Plataforma não suportada: ${this.platform}`);
    }
  }

  // =============================================
  // macOS (Keychain)
  // =============================================

  private async listMacOSCertificates(): Promise<CertificateInfo[]> {
    const certificates: CertificateInfo[] = [];

    try {
      // Listar certificados do Keychain com chave privada
      const output = execSync(
        'security find-identity -v -p codesigning 2>/dev/null || security find-identity -v',
        { encoding: 'utf-8' }
      );

      const lines = output.split('\n');
      for (const line of lines) {
        // Formato: 1) HASH "Nome do Certificado"
        const match = line.match(/^\s*\d+\)\s+([A-F0-9]+)\s+"(.+)"$/);
        if (match) {
          const [, hash, name] = match;

          // Obter detalhes do certificado
          try {
            const details = execSync(
              `security find-certificate -c "${name}" -p | openssl x509 -noout -subject -issuer -dates -serial 2>/dev/null`,
              { encoding: 'utf-8' }
            );

            const certInfo = this.parseCertificateDetails(hash, name, details, 'system');
            if (certInfo) {
              certificates.push(certInfo);
            }
          } catch {
            // Certificado pode não estar acessível
            certificates.push({
              id: hash,
              name,
              subject: name,
              issuer: 'Desconhecido',
              serialNumber: hash.substring(0, 16),
              validFrom: new Date(),
              validTo: new Date(),
              isExpired: false,
              hasPrivateKey: true,
              provider: 'system',
            });
          }
        }
      }
    } catch (error) {
      console.error('Erro ao listar certificados macOS:', error);
    }

    return certificates;
  }

  private async signMacOS(certId: string, _pin: string, data: Buffer): Promise<Buffer> {
    // No macOS, o sistema pede o PIN automaticamente via GUI
    // Usamos o comando security para assinar

    const dataB64 = data.toString('base64');

    // Criar arquivo temporário com os dados
    const tmpFile = `/tmp/iudex-sign-${Date.now()}`;
    const signedFile = `${tmpFile}.sig`;

    try {
      // Escrever dados para arquivo
      require('fs').writeFileSync(tmpFile, data);

      // Assinar com o certificado
      // Nota: Isso vai abrir o diálogo de PIN do macOS
      execSync(
        `security cms -S -N "${certId}" -i "${tmpFile}" -o "${signedFile}"`,
        { encoding: 'utf-8' }
      );

      // Ler assinatura
      const signature = require('fs').readFileSync(signedFile);

      // Limpar arquivos temporários
      require('fs').unlinkSync(tmpFile);
      require('fs').unlinkSync(signedFile);

      return signature;
    } catch (error) {
      // Limpar arquivos temporários em caso de erro
      try {
        require('fs').unlinkSync(tmpFile);
        require('fs').unlinkSync(signedFile);
      } catch {}

      throw error;
    }
  }

  // =============================================
  // Windows (Certificate Store)
  // =============================================

  private async listWindowsCertificates(): Promise<CertificateInfo[]> {
    const certificates: CertificateInfo[] = [];

    try {
      // PowerShell para listar certificados com chave privada
      const script = `
        Get-ChildItem -Path Cert:\\CurrentUser\\My |
        Where-Object { $_.HasPrivateKey } |
        Select-Object -Property Thumbprint, Subject, Issuer, NotBefore, NotAfter, SerialNumber |
        ConvertTo-Json -Compress
      `;

      const output = execSync(`powershell -Command "${script}"`, { encoding: 'utf-8' });
      const certs = JSON.parse(output || '[]');

      for (const cert of Array.isArray(certs) ? certs : [certs]) {
        if (!cert) continue;

        certificates.push({
          id: cert.Thumbprint,
          name: this.parseSubjectCN(cert.Subject),
          subject: cert.Subject,
          issuer: cert.Issuer,
          serialNumber: cert.SerialNumber,
          validFrom: new Date(cert.NotBefore),
          validTo: new Date(cert.NotAfter),
          isExpired: new Date(cert.NotAfter) < new Date(),
          hasPrivateKey: true,
          provider: 'system',
        });
      }
    } catch (error) {
      console.error('Erro ao listar certificados Windows:', error);
    }

    return certificates;
  }

  private async signWindows(certId: string, _pin: string, data: Buffer): Promise<Buffer> {
    // No Windows, usamos SignTool ou PowerShell
    // O PIN é solicitado automaticamente pelo CSP (Cryptographic Service Provider)

    const dataB64 = data.toString('base64');

    const script = `
      $cert = Get-ChildItem -Path Cert:\\CurrentUser\\My\\${certId}
      $bytes = [System.Convert]::FromBase64String('${dataB64}')
      $signature = $cert.PrivateKey.SignData($bytes, [System.Security.Cryptography.HashAlgorithmName]::SHA256, [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
      [System.Convert]::ToBase64String($signature)
    `;

    try {
      const output = execSync(`powershell -Command "${script}"`, { encoding: 'utf-8' });
      return Buffer.from(output.trim(), 'base64');
    } catch (error) {
      throw new Error(`Erro ao assinar: ${error}`);
    }
  }

  // =============================================
  // Linux (PKCS#11 / OpenSC)
  // =============================================

  private async listLinuxCertificates(): Promise<CertificateInfo[]> {
    const certificates: CertificateInfo[] = [];

    try {
      // Tentar com pkcs11-tool (OpenSC)
      const output = execSync(
        'pkcs11-tool --list-objects --type cert 2>/dev/null',
        { encoding: 'utf-8' }
      );

      const certBlocks = output.split('Certificate Object');
      for (const block of certBlocks.slice(1)) {
        const labelMatch = block.match(/label:\s+(.+)/);
        const idMatch = block.match(/ID:\s+([a-f0-9]+)/i);

        if (labelMatch && idMatch) {
          certificates.push({
            id: idMatch[1],
            name: labelMatch[1].trim(),
            subject: labelMatch[1].trim(),
            issuer: 'Token USB',
            serialNumber: idMatch[1],
            validFrom: new Date(),
            validTo: new Date(Date.now() + 365 * 24 * 60 * 60 * 1000),
            isExpired: false,
            hasPrivateKey: true,
            provider: 'token',
          });
        }
      }
    } catch {
      // pkcs11-tool não disponível ou nenhum token conectado
    }

    // Tentar com certificados do sistema
    try {
      const output = execSync(
        'find /etc/ssl/certs -name "*.pem" -type f 2>/dev/null | head -10',
        { encoding: 'utf-8' }
      );

      // Não incluir certificados do sistema sem chave privada
    } catch {}

    return certificates;
  }

  private async signLinux(certId: string, pin: string, data: Buffer): Promise<Buffer> {
    // Usar pkcs11-tool para assinar
    const dataB64 = data.toString('base64');
    const tmpFile = `/tmp/iudex-sign-${Date.now()}`;

    try {
      require('fs').writeFileSync(tmpFile, data);

      const output = execSync(
        `echo "${pin}" | pkcs11-tool --sign --id ${certId} --mechanism SHA256-RSA-PKCS --input-file "${tmpFile}" --pin-stdin`,
        { encoding: 'buffer' }
      );

      require('fs').unlinkSync(tmpFile);
      return output;
    } catch (error) {
      try {
        require('fs').unlinkSync(tmpFile);
      } catch {}
      throw error;
    }
  }

  // =============================================
  // Helpers
  // =============================================

  private parseCertificateDetails(
    id: string,
    name: string,
    details: string,
    provider: 'system' | 'token' | 'file'
  ): CertificateInfo | null {
    try {
      const subject = details.match(/subject=(.+)/)?.[1] || name;
      const issuer = details.match(/issuer=(.+)/)?.[1] || 'Desconhecido';
      const notBefore = details.match(/notBefore=(.+)/)?.[1];
      const notAfter = details.match(/notAfter=(.+)/)?.[1];
      const serial = details.match(/serial=([A-F0-9]+)/i)?.[1] || id.substring(0, 16);

      const validFrom = notBefore ? new Date(notBefore) : new Date();
      const validTo = notAfter ? new Date(notAfter) : new Date();

      return {
        id,
        name: this.parseSubjectCN(subject) || name,
        subject,
        issuer,
        serialNumber: serial,
        validFrom,
        validTo,
        isExpired: validTo < new Date(),
        hasPrivateKey: true,
        provider,
      };
    } catch {
      return null;
    }
  }

  private parseSubjectCN(subject: string): string {
    const match = subject.match(/CN\s*=\s*([^,]+)/i);
    return match?.[1]?.trim() || subject;
  }
}
