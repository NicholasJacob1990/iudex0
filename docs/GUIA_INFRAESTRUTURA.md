# Guia de Infraestrutura — Iudex

> Comparativo completo de custos e estrategias de deploy para Neo4j + Qdrant + OpenSearch.

---

## Os 3 Bancos do Iudex (resumo para leigos)

| Banco | Apelido | O que faz | Exemplo |
|-------|---------|-----------|---------|
| **Neo4j** | O Genealogista | Mapeia conexoes entre leis, decisoes e precedentes | "A Sumula 123 do STJ cita o Art. 5 da CF" |
| **Qdrant** | O Bibliotecario Intuitivo | Busca por significado (semantica) | Voce busca "negligencia hospitalar", ele acha "impericia cirurgica" |
| **OpenSearch** | O Arquivista Metodico | Busca por texto exato (full-text) | Acha "Art. 927, paragrafo unico, do CC" em milhoes de docs |

**Por que os 3 juntos?** Um advogado pesquisa "dano moral por atraso de voo":

1. **OpenSearch** acha docs que mencionam "atraso de voo" literalmente
2. **Qdrant** encontra decisoes sobre "cancelamento de viagem aerea" (mesmo tema, palavras diferentes)
3. **Neo4j** conecta: "essa decisao do STJ cita aquela do STF, que se baseia no Art. 14 do CDC"

---

## Cenario 1: Tudo Managed Cloud (Zero DevOps)

### Neo4j Aura

| Plano | RAM | Preco/mes | Multi-DB | SLA |
|-------|-----|-----------|----------|-----|
| Free | ~200MB | $0 | Nao | Nenhum |
| Professional | 1GB | $65 | Nao | Best-effort |
| Professional | 2GB | $130 | Nao | Best-effort |
| Professional | 4GB | $260 | Nao | Best-effort |
| Professional | 8GB | $520 | Nao | Best-effort |
| Business Critical | 2GB | $292 | Sim | 99.95% + 24/7 |
| Business Critical | 4GB | $584 | Sim | 99.95% + 24/7 |
| Business Critical | 8GB | $1.168 | Sim | 99.95% + 24/7 |

> **Nota:** Multi-database (necessario para isolamento real de tenants) so existe no Business Critical. O Professional filtra por properties apenas.

### Qdrant Cloud

Qdrant nao publica precos fixos — usa calculadora dinamica.

| Config | Estimativa/mes | Notas |
|--------|---------------|-------|
| Free (1GB) | $0 | ~1M vetores de 768 dim |
| ~4GB RAM, 1 no | ~$85-120 | Estimativa de mercado |
| ~8GB RAM, 1 no | ~$155-200 | Baseado em calculadora terceira |
| ~16GB RAM, 2 nos (HA) | ~$350-450 | Com replicacao |
| Hybrid Cloud | a partir de $0.014/hr (~$10/mes min) | Bring your own infra |

Para valores exatos: https://cloud.qdrant.io/calculator

### Amazon OpenSearch Service

| Config | Instancia | Preco/mes | Notas |
|--------|-----------|-----------|-------|
| Free Tier | t3.small (2GB) | $0 | 750hrs/mes, 12 meses |
| t3.small (2GB) | 1 no | ~$26 | Minimo viavel |
| t3.medium (4GB) | 1 no | ~$54 | Dev/staging |
| t3.medium (4GB) | 2 nos (HA) | ~$108 | Producao basica |
| t3.medium (4GB) | 3 nos (Multi-AZ) | ~$162 | Producao com DLS |
| Serverless | min 2 OCU | ~$345 | Minimo fixo alto |
| + EBS Storage | gp3 | ~$0.08/GB/mes | Adicional |

> Reserved Instance (1 ano): ~18-35% desconto sobre on-demand.

### Total Managed Cloud por Cenario

| Cenario | Neo4j | Qdrant | OpenSearch | Total/mes |
|---------|-------|--------|-----------|-----------|
| MVP/Dev | Free | Free (1GB) | Free Tier | $0 |
| Producao minima | Professional 2GB ($130) | ~4GB ($100) | t3.medium 1 no ($54) | ~$284 |
| Producao com HA | Professional 4GB ($260) | ~8GB ($170) | t3.medium 2 nos ($108) | ~$538 |
| Multi-tenant real | Business Critical 4GB ($584) | ~16GB HA ($400) | t3.medium 3 nos ($162) | ~$1.146 |
| Enterprise | Business Critical 8GB ($1.168) | ~32GB HA ($800) | r6g.large 3 nos (~$500) | ~$2.468 |

---

## Cenario 2: Self-Hosted em VPS (Maxima Economia)

### Hetzner Cloud — O que e?

Hetzner e cloud, mas cloud "raiz". Eles fornecem um servidor virtual (VPS) na nuvem deles, com IP proprio, e voce instala o que quiser via SSH/Docker.

| Tipo | Exemplo | O que faz | Analogia |
|------|---------|-----------|----------|
| Cloud gerenciado | Neo4j Aura, Qdrant Cloud, AWS | Entrega o banco pronto, voce so usa | Pedir pizza pronta |
| Cloud VPS | Hetzner, DigitalOcean, Vultr | Te da uma maquina vazia, voce instala tudo | Alugar uma cozinha equipada |
| On-premise | Servidor fisico no escritorio | Compra o hardware | Construir sua propria cozinha |

Dados ficam nos data centers Hetzner (Alemanha, Finlandia ou EUA), acessiveis pela internet.

### Opcoes de Servidor

**3 VPS separados:**

| Servidor | Specs | Preco/mes | Servicos |
|----------|-------|-----------|----------|
| CX32 | 4 vCPU, 8GB RAM, 80GB NVMe | EUR 6,80 (~$8) | Neo4j + Redis |
| CX32 | 4 vCPU, 8GB RAM, 80GB NVMe | EUR 6,80 (~$8) | Qdrant |
| CX32 | 4 vCPU, 8GB RAM, 80GB NVMe | EUR 6,80 (~$8) | OpenSearch |
| **Total 3 VPS** | | **~$24/mes** | |

**Tudo em 1 servidor maior:**

| Servidor | Specs | Preco/mes | Servicos |
|----------|-------|-----------|----------|
| CX42 | 8 vCPU, 16GB RAM, 160GB NVMe | EUR 16,40 (~$19) | Tudo via Docker Compose |
| CCX23 (dedicado) | 4 vCPU, 16GB RAM, 160GB NVMe | EUR 29,72 (~$34) | Melhor para producao |
| CX52 | 16 vCPU, 32GB RAM, 320GB NVMe | EUR 36,40 (~$42) | Com folga |

### Total Self-Hosted por Cenario

| Cenario | Infra | Preco/mes | Trade-off |
|---------|-------|-----------|-----------|
| Dev/MVP | CX42 (16GB, tudo junto) | ~$19 | Sem HA, sem backups automaticos |
| Producao basica | 3x CX32 (8GB cada) | ~$24 | Separacao de servicos |
| Producao dedicada | 3x CCX13 (8GB ded.) | ~$52 | vCPU dedicada |
| Producao robusta | CX52 + CX32 backup | ~$50 | Com replica |

---

## Cenario 3: Hibrido (Self-Hosted + Managed)

### Opcao A — Neo4j managed, resto self-hosted

| Servico | Deployment | Preco/mes | Justificativa |
|---------|-----------|-----------|---------------|
| Neo4j | Aura Professional 2GB | $130 | Grafo e critico, backups automaticos |
| Qdrant | Self-hosted Hetzner CX32 | ~$8 | Open-source, Docker simples |
| OpenSearch | Self-hosted Hetzner CX32 | ~$8 | Open-source, Docker simples |
| Redis | Junto com OpenSearch | $0 | Compartilhado |
| **Total** | | **~$146/mes** | |

### Opcao B — Prioridade invertida

| Servico | Deployment | Preco/mes | Justificativa |
|---------|-----------|-----------|---------------|
| Neo4j | Self-hosted Hetzner (Community) | ~$8 | Sem multi-DB, mas funciona com properties |
| Qdrant | Cloud managed 4GB | ~$100 | Vector search precisa de performance |
| OpenSearch | AWS t3.medium | ~$54 | DLS nativo para multi-tenancy |
| **Total** | | **~$162/mes** | |

---

## Comparativo Resumido

| Estrategia | Custo/mes | DevOps necessario | Multi-tenant | Observacao |
|-----------|-----------|-------------------|-------------|-----------|
| Tudo Free Tier | $0 | Nenhum | Nao | So para dev |
| Self-hosted Hetzner | $19-52 | Alto | Sim (app-layer) | Mais barato, mais trabalho |
| Hibrido | $146-162 | Medio | Parcial | Bom equilibrio |
| Managed producao | $284-538 | Baixo | Parcial | Confortavel |
| Managed enterprise | $1.146-2.468 | Minimo | Total (DB-level) | Multi-tenant real |

### Em Reais (referencia)

| Opcao | Custo/mes | Analogia |
|-------|-----------|----------|
| Self-hosted | ~R$ 110 | Voce compra os ingredientes e cozinha |
| Hibrido | ~R$ 850 | Parte em casa, parte terceirizado |
| Tudo na nuvem | R$ 1.650-3.100 | Terceiriza tudo, so usa |
| Enterprise | R$ 6.700-14.400 | Hotel 5 estrelas com concierge |

---

## DevOps: O que precisa no Self-Hosted?

### Setup inicial (uma vez)

1. Criar conta no Hetzner
2. Criar VPS (CX42, 16GB)
3. Apontar dominio (api.iudex.com.br -> IP do servidor)
4. SSH no servidor
5. Instalar Docker + Docker Compose
6. Clonar o repo
7. Subir `docker-compose.yml`
8. Configurar HTTPS (Caddy ou Nginx + Let's Encrypt)

### Manutencao de rotina

| Tarefa | Frequencia | Esforco | Automatizavel? |
|--------|-----------|---------|---------------|
| Backups | Diario | 0 (apos configurar) | Sim, cron job |
| Monitorar se ta online | Continuo | 0 | Sim, UptimeRobot (gratis) |
| Atualizar Docker images | Mensal | 10 min | Sim, Watchtower |
| Ver logs se algo quebrar | Quando acontecer | 15-30 min | Parcial |
| Atualizar SO do servidor | Mensal | 5 min | Sim, unattended-upgrades |
| Renovar SSL | Nunca | 0 | Let's Encrypt renova sozinho |

**Na pratica: ~30 minutos por mes depois do setup.**

### O que pode dar errado

| Problema | Probabilidade | Solucao |
|----------|-------------|---------|
| Servidor cai | Baixa (Hetzner e estavel) | Reinicia pelo painel web, 2 min |
| Disco enche | Media (logs, dados) | Alerta automatico + limpeza |
| Banco corrompe | Baixa | Restaura backup |
| Invasao | Baixa (se configurar firewall) | Recria servidor do zero + backup |
| Ficou lento | Media (crescimento de dados) | Migra pra VPS maior, ~1 hora |

### O que NAO precisa

- ~~Kubernetes~~ — Docker Compose resolve
- ~~CI/CD complexo~~ — `git pull && docker compose up -d`
- ~~Monitoramento enterprise~~ — UptimeRobot gratis + logs do Docker
- ~~Engenheiro DevOps~~ — Um dev fullstack da conta
- ~~Load balancer~~ — Um servidor aguenta centenas de usuarios

### Automacao minima viavel

```bash
# Backup diario — roda todo dia as 3h da manha
# Faz dump dos 3 bancos + envia pra storage externo
0 3 * * * /opt/iudex/scripts/backup.sh
```

UptimeRobot (gratis) pinga o servidor a cada 5 min e manda alerta no Telegram se cair.

---

## Recomendacao para o Iudex

### Fase 1: MVP/Validacao

**Hetzner CX42 (16GB RAM) — ~R$ 100/mes**

O `docker-compose.yml` do Iudex ja existe. Deploy e basicamente:
1. Criar VPS
2. Instalar Docker
3. Subir o compose
4. Funciona igual ao Mac, mas acessivel online

### Fase 2: Primeiros clientes pagantes

**Neo4j Aura Professional + resto self-hosted — ~R$ 850/mes**

Migrar o grafo para managed (critico), manter Qdrant + OpenSearch no Hetzner.

### Fase 3: Escala

**Tudo managed — R$ 3.000+/mes**

Neo4j Business Critical + Qdrant Cloud + OpenSearch managed. Nesse ponto ja deve haver receita justificando.

### Principio

> Nao pague R$ 1.750/mes antes de ter clientes. Valida barato, escala quando der certo.

| Pergunta | Resposta |
|----------|---------|
| Preciso de DevOps dedicado? | Nao |
| Preciso saber Linux? | Basico (ssh, docker, nano) |
| Quanto tempo gasto por mes? | ~30 min em media |
| Quando preciso de DevOps real? | Quando tiver +50 clientes simultaneos |

---

## Fontes

- https://neo4j.com/pricing/
- https://qdrant.tech/pricing/
- https://cloud.qdrant.io/calculator
- https://aws.amazon.com/opensearch-service/pricing/
- https://www.hetzner.com/cloud/pricing/
- https://qdrant.tech/documentation/cloud-pricing-payments/
