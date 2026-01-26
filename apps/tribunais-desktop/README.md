# Iudex Tribunais Desktop

App desktop para assinatura com certificado A3 físico (token USB) em tribunais brasileiros.

## Funcionalidades

- **Conexão WebSocket** com servidor Iudex
- **Detecção de certificados** no sistema (Keychain, Windows Store, PKCS#11)
- **Assinatura digital** com tokens USB
- **Interface simples** para aprovar operações
- **Tray icon** para execução em background

## Plataformas Suportadas

| Plataforma | Método de Acesso a Certificados |
|------------|--------------------------------|
| macOS | Keychain + security CLI |
| Windows | Certificate Store + PowerShell |
| Linux | PKCS#11 / OpenSC |

## Instalação

```bash
# Instalar dependências
pnpm install

# Desenvolvimento
pnpm dev

# Build
pnpm build

# Empacotar para distribuição
pnpm package        # Todas as plataformas
pnpm package:mac    # macOS (.dmg, .zip)
pnpm package:win    # Windows (.exe, portable)
pnpm package:linux  # Linux (.AppImage, .deb)
```

## Uso

1. Abra o app
2. Configure seu **ID de Usuário** (mesmo do Iudex)
3. Configure o **Servidor** (ex: `ws://localhost:3101`)
4. Clique em **Conectar**
5. Conecte seu token USB
6. Quando uma operação de assinatura for solicitada:
   - Selecione o certificado na lista
   - Digite o PIN
   - Clique em **Assinar**

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│ App Desktop (Electron)                                   │
│                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │ Main Process│◄──►│ WebSocket   │◄──►│ Servidor    │ │
│  │             │    │ Client      │    │ Iudex       │ │
│  └──────┬──────┘    └─────────────┘    └─────────────┘ │
│         │                                               │
│  ┌──────▼──────┐    ┌─────────────┐                    │
│  │ Certificate │    │ Renderer    │                    │
│  │ Manager     │    │ (UI)        │                    │
│  └──────┬──────┘    └─────────────┘                    │
│         │                                               │
│  ┌──────▼──────┐                                       │
│  │ Token USB   │                                       │
│  │ (PKCS#11)   │                                       │
│  └─────────────┘                                       │
└─────────────────────────────────────────────────────────┘
```

## Fluxo de Assinatura

1. Usuário inicia peticionamento no Iudex (web)
2. Servidor detecta que credencial requer A3 físico
3. Servidor envia comando via WebSocket para o app desktop
4. App desktop mostra notificação e popup
5. Usuário seleciona certificado e digita PIN
6. App desktop assina dados e envia de volta ao servidor
7. Servidor conclui a petição

## Configuração

As configurações são salvas em:
- macOS: `~/Library/Application Support/iudex-tribunais-desktop/config.json`
- Windows: `%APPDATA%/iudex-tribunais-desktop/config.json`
- Linux: `~/.config/iudex-tribunais-desktop/config.json`

```json
{
  "serverUrl": "ws://localhost:3101",
  "userId": "user123",
  "autoConnect": true,
  "minimizeToTray": true
}
```

## Requisitos

- Node.js 18+
- Token USB com driver PKCS#11 instalado
- Para Linux: `opensc` e `pkcs11-tool`

## Troubleshooting

### Certificado não aparece na lista

**macOS:**
```bash
# Verificar certificados no Keychain
security find-identity -v
```

**Windows:**
```powershell
# Listar certificados com chave privada
Get-ChildItem -Path Cert:\CurrentUser\My | Where-Object { $_.HasPrivateKey }
```

**Linux:**
```bash
# Verificar se o token é detectado
pkcs11-tool --list-slots
pkcs11-tool --list-objects --type cert
```

### Erro ao assinar

- Verifique se o PIN está correto
- Verifique se o certificado não expirou
- No Linux, verifique se o `pcscd` está rodando: `sudo systemctl status pcscd`

## Desenvolvimento

```bash
# Modo dev com hot reload
pnpm dev

# Logs do main process
# São exibidos no terminal

# DevTools do renderer
# Pressione Cmd/Ctrl+Shift+I no app
```

## Licença

MIT
