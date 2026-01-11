import os
import sys
import asyncio
from google.genai import types
from google.genai import Client
from dotenv import load_dotenv

load_dotenv()

PROMPT_STRUCTURE_REVIEW = """Você é um revisor especializado em estrutura de documentos jurídicos educacionais.

## TAREFA
Revise a ESTRUTURA (headers/títulos) do documento abaixo e corrija os seguintes problemas:

### 1. QUESTÕES DUPLICADAS
Se duas seções têm o mesmo número de questão na mesma área do direito, MESCLE-AS:
- ERRADO: "2.1. Questão 1: TAC" + "2.2. Questão 1: TAC" 
- CORRETO: "2.1. Questão 1: TAC" (única, com todo o conteúdo)

### 2. SUBTÓPICOS ÓRFÃOS
Se um subtópico começa com "A.", "B.", "C." mas está como item principal (##), mova-o para dentro da questão anterior:
- ERRADO: "## 2.4. A. Natureza Jurídica do Parecer"
- CORRETO: "### 2.3.1. Natureza Jurídica do Parecer" (sob a Questão 2)

### 3. FRAGMENTAÇÃO EXCESSIVA
Se uma seção como "Considerações Finais" ou "Dúvidas" tem mais de 5-6 subtópicos muito granulares, agrupe-os:
- ERRADO: 8.1, 8.2, 8.3... 8.13 (13 subtópicos!)
- CORRETO: 8.1 Estratégia de Prova, 8.2 Materiais de Apoio (3-5 grupos)

### 4. NUMERAÇÃO E METADATA
- Remova header "[TIPO: SIMULADO]"
- Garanta numeração sequencial correta (Questão 1, 2, 3...)
- **QUESTÃO 5**: Verifique se há duplicação e mescle.
- **QUESTÃO 6**: Verifique se foi pulada e renomeie o item correspondente.

## REGRAS CRÍTICAS
⚠️ ATENÇÃO MÁXIMA:
- **NÃO ALTERE O CONTEÚDO** dos parágrafos, apenas os títulos/headers
- **NUNCA RESUMA OU ENCURTE** o texto - o output deve ter o MESMO tamanho do input
- **COPIE INTEGRALMENTE** todos os parágrafos, tabelas e listas
- **MANTENHA** toda informação técnica e jurídica
- **PRESERVE** a ordem cronológica geral
- Use MÁXIMO 3 níveis de hierarquia (##, ###, ####)

## DOCUMENTO PARA REVISAR:
{documento}

## RESPOSTA:
Retorne o documento COMPLETO E INTEGRAL (mesmo tamanho do original) com apenas os títulos/headers corrigidos. NÃO RESUMA."""

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

# Configurar Vertex AI (Project ID extraído dos logs de erro anteriores)
PROJECT_ID = "745699796447"
LOCATION = "us-central1"

async def main():
    print(f"☁️  Inicializando Vertex AI ({LOCATION})...")
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    
    model = GenerativeModel("gemini-1.5-pro-002")
    
    input_file = "aula_audio_RAW_APOSTILA.md"
    output_file = "aula_audio_RAW_APOSTILA_REVISED.md"
    
    print(f"📖 Lendo {input_file}...")
    with open(input_file, "r") as f:
        texto = f.read()
        
    print(f"🧠 Enviando para revisão IA (Vertex AI - gemini-1.5-pro-002)...")
    
    # Truncar se necessário (Vertex suporta 1M/2M dependendo do modelo, mas 128k output limit)
    # Output limit do 1.5 Pro é 8192 tokens? Não, na Vertex é configurável.
    
    try:
        response = model.generate_content(
            PROMPT_STRUCTURE_REVIEW.format(documento=texto),
            generation_config=GenerationConfig(
                max_output_tokens=8192, # Vertex as vezes limita output.
                temperature=0.0
            )
        )
        
        resultado = response.text.replace('```markdown', '').replace('```', '').strip()
        
        if len(resultado) < len(texto) * 0.5:
             # Se cortou muito, pode ser o limite de tokens de saída.
             print(f"⚠️ AVISO: Resultado muito curto ({len(resultado)} vs {len(texto)}). Verifique limite de tokens.")
        
        print(f"💾 Salvando em {output_file}...")
        with open(output_file, "w") as f:
            f.write(resultado)
            
        print("✅ Concluído!")
        
    except Exception as e:
        print(f"❌ Erro Vertex AI: {e}")

if __name__ == "__main__":
    asyncio.run(main())
