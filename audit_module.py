import os
import sys
import logging
from google import genai
from google.genai import types
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# Carrega .env se disponível (mantém compatibilidade com mlx_vomo.py)
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except Exception:
    pass

# Configuração de Credenciais (Standalone) - espelha mlx_vomo.py
PRIMARY_CREDENTIALS_PATH = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/gen-lang-client-0727883752-f72a632e4ec2.json"
FALLBACK_CREDENTIALS_PATH = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/vertex_credentials.json"

def _configure_vertex_credentials():
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    for path in (PRIMARY_CREDENTIALS_PATH, FALLBACK_CREDENTIALS_PATH):
        if path and os.path.exists(path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
            logger.info(f"🔑 Credenciais Vertex carregadas de: {path}")
            return

_configure_vertex_credentials()

# Configuração de Logger para o módulo
logger = logging.getLogger(__name__)

PROMPT_AUDITORIA_SOLO = """
ATUE COMO UM AUDITOR JURÍDICO SÊNIOR (REVISOR DE APOSTILAS DE CONCURSO).

Sua tarefa é ler a apostila fornecida e identificar ERROS GRAVES, ALUCINAÇÕES JURÍDICAS ou PROBLEMAS DE REDAÇÃO.
O foco é a FIDELIDADE TÉCNICA e a CONSISTÊNCIA.

Analise o texto procurando por:

1.  🔴 **CONTRADIÇÕES JURÍDICAS:**
    *   O texto afirma algo que é notoriamente falso no Direito Brasileiro?
    *   O texto se contradiz (ex: diz que é "obrigatório" e depois "facultativo")?

2.  🔴 **CITAÇÕES MAL FORMATADAS OU IMPRECISAS:**
    *   Leis citadas sem número ou artigo (ex: "segundo a lei..." sem dizer qual).
    *   Súmulas com numeração errada ou inexistente.
    *   Jurisprudência inventada (Hallucination).

3.  🔴 **DATAS SUSPEITAS:**
    *   Leis recentes com datas antigas ou vice-versa.
    *   Prazos processuais errados.

4.  🔴 **PROBLEMAS DE INTEGRIDADE DO TEXTO:**
    *   Frases interrompidas ou incompletas.
    *   Trechos desconexos (que não fazem sentido com o parágrafo anterior).
    *   Duplicidades de parágrafos inteiros.

5.  🔴 **ALUCINAÇÃO DE IA (COM CAUTELA EM LEIS RECENTES):**
    *   Trechos que parecem "embromação" ou fogem do tom.
    *   **ATENÇÃO:** Para leis datadas de **2024, 2025 ou 2026** (ex: Reforma Tributária, novas Leis Complementares), o seu conhecimento pode estar desatualizado.
    *   **REGRA DE OURO:** Se encontrar uma lei recente que você "acha" que não existe, **NÃO MARQUE COMO ERRO**. Marque como "⚠️ **VERIFICAR NOVIDADE LEGISLATIVA**" e peça para o aluno conferir, pois pode ser uma lei aprovada após seu treinamento.

---
**SAÍDA ESPERADA:**

Gere um RELATÓRIO DE AUDITORIA em Markdown no seguinte formato:

# 🕵️ Relatório de Auditoria Jurídica

## 1. Resumo Geral
(Dê uma nota de 0 a 10 para a confiabilidade jurídica do texto. Resuma a qualidade geral em 2 linhas.)

## 2. Pontos de Atenção (Críticos)
(Liste apenas se houver erros. Se não houver, escreva "Nenhum erro grave detectado.")

*   **[TIPO DE ERRO]** "Trecho do texto original..."
    *   *Problema:* Explique o erro.
    *   *Sugestão:* Como corrigir.

## 3. Dispositivos Legais Citados (Checklist)
(Liste brevemente as leis/súmulas citadas para conferência rápida)
*   Súmula X
*   Lei Y

---
<texto_para_auditar>
{texto}
</texto_para_auditar>
"""

PROMPT_AUDITORIA_CONTRA_RAW = """
ATUE COMO UM AUDITOR DE FIDELIDADE PARA APOSTILAS JURÍDICAS.

## FONTE DA VERDADE (REGRA ABSOLUTA)
A TRANSCRIÇÃO BRUTA (RAW) é a fonte da verdade desta auditoria.
- NÃO use conhecimento jurídico externo para dizer que a aula está “errada”.
- Sua função é detectar problemas introduzidos pela formatação (adições, distorções, omissões, troca de números).

## SEU OBJETIVO
Compare o RAW com a APOSTILA FORMATADA e identifique:

1) 🔴 ADIÇÕES / ALUCINAÇÕES (a apostila traz algo que não existe no RAW)
   - Conceitos, regras, exceções, exemplos, macetes, “pegadinhas”.
   - NÚMEROS: leis, artigos, súmulas, temas, REsp/RE/ADI, prazos, percentuais, valores.

2) 🔴 DISTORÇÕES DE SENTIDO (RAW diz X, apostila diz Y)
   - Ex.: “facultativo” ↔ “obrigatório”, regra ↔ exceção, troca de sujeito, troca de prazo, generalização indevida.

3) 🔴 ALTERAÇÃO DE REFERÊNCIAS (mudou/omitiu número ou identificação)
   - Ex.: Lei 11.101/2005 virou “Lei de Falências” sem número; Súmula 7 virou Súmula 17; perdeu artigo/inciso.

4) 🔴 OMISSÕES CRÍTICAS (algo relevante do RAW sumiu na apostila)
   - Especialmente dispositivos/números, passos de procedimento, dicas de prova e pontos enfatizados pelo professor.

5) 🟠 INTEGRIDADE / REDAÇÃO (problema editorial que compromete entendimento)
   - Frases truncadas, colagens estranhas, repetição integral de parágrafos, trechos sem nexo.

## COMO REPORTAR (CRÍTICO)
- Priorize itens de maior impacto (números/regras/prazos).
- Para cada item crítico, inclua:
  - Trecho curto do RAW que comprova o correto (ou “não encontrado no RAW” se for adição).
  - Trecho curto da APOSTILA onde aparece o problema.
  - Sugestão objetiva: “remover”, “corrigir para X”, “reinserir trecho Y”.
- Limite a lista a no máximo 25 itens (os mais relevantes). Se houver mais, cite “há mais ocorrências”.

---
SAÍDA ESPERADA (Markdown):

# 🕵️ Relatório de Auditoria (RAW x Apostila)

## 1. Resumo Geral
- Nota de fidelidade (0–10): X/10
- Síntese (2 linhas)

## 2. Pontos de Atenção (Críticos)
(Liste itens. Se não houver, escreva "Nenhum problema crítico detectado.")

## 3. Omissões Relevantes
(Liste. Se não houver, escreva "Nenhuma omissão relevante detectada.")

## 4. Checklist de Referências Numéricas
(Liste leis/súmulas/artigos/julgados mencionados na apostila para conferência rápida.)

---
<transcricao_bruta>
{raw}
</transcricao_bruta>

<apostila_formatada>
{formatted}
</apostila_formatada>
"""

def _resolve_audit_provider() -> str:
    provider = (os.getenv("AUDIT_PROVIDER") or "").strip().lower()
    if provider in ("openai", "gpt"):
        return "openai"
    if provider in ("gemini_api", "google_api", "api"):
        return "gemini_api"
    if provider in ("vertex", "vertexai", "gcp"):
        return "vertex"
    # Auto: segue lógica do mlx_vomo.py
    auth_mode = (os.getenv("IUDEX_GEMINI_AUTH") or "auto").strip().lower()
    if auth_mode in ("apikey", "api_key", "key", "dev", "developer", "ai-studio", "aistudio"):
        return "gemini_api"
    if auth_mode in ("vertex", "vertexai", "gcp"):
        return "vertex"
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    has_vertex_creds = bool(os.getenv("GOOGLE_CLOUD_PROJECT")) or bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    return "vertex" if has_vertex_creds or not bool(api_key) else "gemini_api"


def _build_gemini_client(provider: str):
    if provider == "gemini_api":
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY/GEMINI_API_KEY não configurada para gemini_api.")
        return genai.Client(api_key=api_key)
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or "gen-lang-client-0727883752"
    location = (os.getenv("VERTEX_AI_LOCATION") or "us-central1").strip()
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if api_key and os.getenv("GOOGLE_APPLICATION_CREDENTIALS") is None:
        return genai.Client(vertexai=True, api_key=api_key)
    return genai.Client(vertexai=True, project=project_id, location=location)


def _run_audit_with_openai(prompt: str) -> str:
    if not OpenAI:
        raise RuntimeError("openai não instalado.")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY não configurada.")
    model = os.getenv("AUDIT_OPENAI_MODEL", "gpt-5-mini-2025-08-07")
    max_tokens = int(os.getenv("AUDIT_OPENAI_MAX_TOKENS", "4000"))
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content if response.choices else None
    if not content:
        raise RuntimeError("Auditoria OpenAI retornou texto vazio.")
    return content


def auditar_consistencia_legal(client, texto_completo, output_path, raw_transcript=None, provider: str = "vertex"):
    """
    Realiza uma auditoria jurídica no texto usando o Gemini Pro/Flash
    e salva o relatório em output_path.
    """
    logger.info("🕵️ Iniciando Auditoria Jurídica Pós-Processamento...")
    
    # Validação de tamanho (Flash aguenta 1M tokens, então geralmente vai caber tudo)
    # Se for MUITO grande, ideal seria chunkar, mas para apostilas de aula (30-50k tokens) é tranquilo.
    
    if raw_transcript:
        logger.info("🧾 Modo: confronto com RAW (fonte da verdade).")
        prompt = PROMPT_AUDITORIA_CONTRA_RAW.format(raw=raw_transcript, formatted=texto_completo)
    else:
        logger.info("ℹ️  Modo: auditoria apenas do texto formatado (sem RAW).")
        prompt = PROMPT_AUDITORIA_SOLO.format(texto=texto_completo)
    
    try:
        if provider == "openai":
            relatorio = _run_audit_with_openai(prompt)
        else:
            response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1, # Temperatura baixa para ser analítico e cético
                    top_p=0.95,
                    max_output_tokens=20000,
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=False,
                        thinking_level="HIGH"  # Auditoria requer raciocínio profundo (mais tokens/tempo)
                    ),
                    safety_settings=[
                        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                    ]
                )
            )
            relatorio = response.text if response.text else None
        
        if relatorio:
            # Adicionar cabeçalho de metadados
            header = f"<!-- Auditoria realizada em: {output_path} -->\n\n"
            full_content = header + relatorio
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_content)
                
            logger.info(f"✅ Relatório de Auditoria salvo: {output_path}")
            return relatorio
            
        logger.warning("⚠️ Auditoria retornou texto vazio.")
        return False

    except Exception as e:
        logger.error(f"❌ Erro na auditoria: {e}")
        # Fallback automático para OpenAI se o Vertex falhar por permissão
        msg = str(e)
        if provider == "vertex" and ("PERMISSION_DENIED" in msg or "403" in msg):
            try:
                logger.info("↩️ Tentando fallback OpenAI para auditoria...")
                relatorio = _run_audit_with_openai(prompt)
                header = f"<!-- Auditoria realizada em: {output_path} -->\n\n"
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(header + relatorio)
                logger.info(f"✅ Relatório de Auditoria salvo: {output_path}")
                return relatorio
            except Exception as openai_exc:
                logger.error(f"❌ Fallback OpenAI falhou: {openai_exc}")
        return False

# Wrapper para execução via linha de comando
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
    
    if len(sys.argv) < 2:
        print("Uso: python audit_module.py <arquivo_markdown_formatado.md> [--raw <arquivo_raw.txt>]")
        sys.exit(1)
        
    md_path = sys.argv[1]
    if not os.path.exists(md_path):
        print(f"Arquivo não encontrado: {md_path}")
        sys.exit(1)

    raw_path = None
    if "--raw" in sys.argv:
        try:
            raw_idx = sys.argv.index("--raw")
            if raw_idx + 1 < len(sys.argv):
                raw_path = sys.argv[raw_idx + 1]
        except ValueError:
            raw_path = None

    # Auto-detect RAW se não foi informado (padrão: confrontar RAW sempre que existir)
    if not raw_path:
        try:
            base_dir = os.path.dirname(md_path)
            base_name = os.path.splitext(os.path.basename(md_path))[0]

            # Tenta padrões comuns: *_RAW.txt e variações
            candidates = [
                os.path.join(base_dir, f"{base_name}_RAW.txt"),
                os.path.join(base_dir, f"{base_name}.txt"),
            ]

            # Fallback: procurar qualquer arquivo "*RAW*.txt" no mesmo diretório
            if base_dir and os.path.isdir(base_dir):
                for fname in os.listdir(base_dir):
                    if fname.lower().endswith(".txt") and "raw" in fname.lower():
                        candidates.append(os.path.join(base_dir, fname))

            for c in candidates:
                if c and os.path.exists(c):
                    raw_path = c
                    break
        except Exception:
            raw_path = raw_path
        
    provider = _resolve_audit_provider()
    client = None
    if provider in ("vertex", "gemini_api"):
        client = _build_gemini_client(provider)
    
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    raw_content = None
    if raw_path and os.path.exists(raw_path):
        try:
            with open(raw_path, 'r', encoding='utf-8', errors='ignore') as rf:
                raw_content = rf.read()
            logger.info(f"🧾 RAW detectado para confronto: {raw_path}")
        except Exception:
            raw_content = None
    elif raw_path:
        if not os.path.exists(raw_path):
            print(f"Arquivo RAW não encontrado: {raw_path}")
            sys.exit(1)
        with open(raw_path, 'r', encoding='utf-8') as f:
            raw_content = f.read()
        
    base_name = os.path.splitext(md_path)[0]
    report_path = f"{base_name}_RELATORIO_AUDITORIA.md"

    auditar_consistencia_legal(client, content, report_path, raw_transcript=raw_content, provider=provider)
