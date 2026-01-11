import os
import sys
import logging
from google import genai
from google.genai import types

# Configuração de Credenciais (Standalone)
CREDENTIALS_PATH = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/vertex_credentials.json"
if os.path.exists(CREDENTIALS_PATH) and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH

# Configuração de Logger para o módulo
logger = logging.getLogger(__name__)

PROMPT_AUDITORIA = """
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

5.  🔴 **ALUCINAÇÕES DE IA:**
    *   Trechos que parecem "embromação" (lero-lero) ou que fogem do tom da aula.

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

def auditar_consistencia_legal(client, texto_completo, output_path):
    """
    Realiza uma auditoria jurídica no texto usando o Gemini Pro/Flash
    e salva o relatório em output_path.
    """
    logger.info("🕵️ Iniciando Auditoria Jurídica Pós-Processamento...")
    
    # Validação de tamanho (Flash aguenta 1M tokens, então geralmente vai caber tudo)
    # Se for MUITO grande, ideal seria chunkar, mas para apostilas de aula (30-50k tokens) é tranquilo.
    
    prompt = PROMPT_AUDITORIA.format(texto=texto_completo)
    
    try:
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
        
        if response.text:
            relatorio = response.text
            
            # Adicionar cabeçalho de metadados
            header = f"<!-- Auditoria realizada em: {output_path} -->\n\n"
            full_content = header + relatorio
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_content)
                
            logger.info(f"✅ Relatório de Auditoria salvo: {output_path}")
            return relatorio
            
        else:
            logger.warning("⚠️ Auditoria retornou texto vazio.")
            return False

    except Exception as e:
        logger.error(f"❌ Erro na auditoria: {e}")
        return False

# Wrapper para execução via linha de comando
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
    
    if len(sys.argv) < 2:
        print("Uso: python audit_module.py <arquivo_markdown_formatado.md>")
        sys.exit(1)
        
    md_path = sys.argv[1]
    if not os.path.exists(md_path):
        print(f"Arquivo não encontrado: {md_path}")
        sys.exit(1)
        
    # Setup Client (Reusa lógica do script principal ou init básico)
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0727883752")
    location = "global"
    
    client = genai.Client(vertexai=True, project=project_id, location=location)
    
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    base_name = os.path.splitext(md_path)[0]
    report_path = f"{base_name}_RELATORIO_AUDITORIA.md"
    
    auditar_consistencia_legal(client, content, report_path)
