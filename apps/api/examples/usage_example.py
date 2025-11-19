"""
Exemplo completo de uso da API Iudex
Demonstra o sistema Multi-Agente em ação
"""

import asyncio
import httpx
from loguru import logger


BASE_URL = "http://localhost:8000"


async def register_user():
    """Registra um novo usuário"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": "advogado@example.com",
                "password": "SenhaSegura123",
                "name": "Dr. João Silva"
            }
        )
        return response.json()


async def login():
    """Faz login e retorna token"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "advogado@example.com",
                "password": "SenhaSegura123"
            }
        )
        data = response.json()
        return data.get("access_token")


async def upload_document(token: str):
    """Upload de um documento"""
    async with httpx.AsyncClient() as client:
        files = {
            "file": ("documento.pdf", open("exemplo.pdf", "rb"), "application/pdf")
        }
        response = await client.post(
            f"{BASE_URL}/api/documents/upload",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
            data={
                "apply_ocr": "false",
                "extract_metadata": "true"
            }
        )
        return response.json()


async def create_chat(token: str):
    """Cria um novo chat"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/chats",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": "Petição Inicial - Danos Morais",
                "mode": "MINUTA",
                "context": {}
            }
        )
        return response.json()


async def generate_document_multi_agent(token: str, chat_id: str):
    """
    Gera documento usando sistema Multi-Agente
    Este é o coração do sistema!
    """
    logger.info("🚀 Iniciando geração com Multi-Agente IA...")
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{BASE_URL}/api/chats/{chat_id}/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "prompt": """
                Elabore uma petição inicial de ação de indenização por danos morais.
                
                FATOS:
                - Autor teve seu nome negativado indevidamente pela empresa XYZ
                - A dívida já estava quitada há 6 meses
                - Autor sofreu constrangimento ao tentar fazer compras
                - Já tentou resolver extrajudicialmente sem sucesso
                
                PEDIDOS:
                - Declaração de inexistência do débito
                - Indenização por danos morais no valor de R$ 20.000,00
                - Tutela de urgência para retirada imediata do nome dos cadastros
                
                Fundamentar em jurisprudência recente do STJ sobre o tema.
                """,
                "effort_level": 5,  # Máximo esforço - todos os agentes!
                "verbosity": "detailed",
                "context": {
                    "user_instructions": "Usar linguagem técnica mas acessível. Foco em jurisprudência recente."
                }
            }
        )
        return response.json()


async def main():
    """Exemplo completo de uso"""
    
    print("=" * 80)
    print("🎯 EXEMPLO DE USO - IUDEX API")
    print("Sistema Multi-Agente: Claude + Gemini + GPT")
    print("=" * 80)
    print()
    
    try:
        # 1. Login (ou usar token existente)
        print("📝 Fazendo login...")
        token = await login()
        print(f"✅ Login realizado! Token: {token[:20]}...")
        print()
        
        # 2. Criar chat
        print("💬 Criando chat...")
        chat = await create_chat(token)
        chat_id = chat["id"]
        print(f"✅ Chat criado: {chat_id}")
        print()
        
        # 3. Gerar documento com Multi-Agente
        print("🤖 Gerando documento com IA Multi-Agente...")
        print("   → Claude Sonnet 4.5 (Gerador)")
        print("   → Gemini 2.5 Pro (Revisor Legal)")
        print("   → GPT-5 (Revisor Textual)")
        print()
        print("⏳ Aguarde... (pode levar ~40 segundos)")
        print()
        
        result = await generate_document_multi_agent(token, chat_id)
        
        # Mostrar resultados
        print("=" * 80)
        print("✅ DOCUMENTO GERADO COM SUCESSO!")
        print("=" * 80)
        print()
        
        print(f"📊 ESTATÍSTICAS:")
        print(f"   • Tokens Usados: {result.get('total_tokens', 0):,}")
        print(f"   • Custo Estimado: R$ {result.get('total_cost', 0):.4f}")
        print(f"   • Tempo de Processamento: {result.get('processing_time', 0):.1f}s")
        print(f"   • Consenso dos Agentes: {'✅ Sim' if result.get('consensus') else '❌ Não'}")
        print()
        
        # Mostrar revisões
        if result.get('reviews'):
            print(f"📝 REVISÕES DOS AGENTES:")
            for i, review in enumerate(result['reviews'], 1):
                agent = review.get('agent_name', 'Agente')
                score = review.get('score', 0)
                approved = review.get('approved', False)
                print(f"   {i}. {agent}")
                print(f"      • Score: {score}/10")
                print(f"      • Aprovado: {'✅' if approved else '❌'}")
            print()
        
        # Mostrar parte do documento
        content = result.get('content', '')
        print(f"📄 DOCUMENTO GERADO ({len(content)} caracteres):")
        print("-" * 80)
        print(content[:500])
        if len(content) > 500:
            print("\n... [documento continua] ...")
        print("-" * 80)
        print()
        
        # Metadados
        metadata = result.get('metadata', {})
        print(f"ℹ️  METADADOS:")
        print(f"   • Agentes Usados: {', '.join(metadata.get('agents_used', []))}")
        print(f"   • Iterações: {metadata.get('iterations', 0)}")
        print(f"   • Nível de Esforço: {metadata.get('effort_level', 0)}/5")
        print()
        
        print("=" * 80)
        print("🎉 SUCESSO! Documento jurídico gerado com qualidade profissional!")
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        logger.exception("Erro no exemplo")


if __name__ == "__main__":
    asyncio.run(main())

