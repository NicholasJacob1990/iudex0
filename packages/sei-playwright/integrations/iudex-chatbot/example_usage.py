"""
Exemplo de uso do SEI Chatbot com múltiplos providers

Execute:
    # Primeiro, inicie a API sei-playwright
    cd ~/Documents/Aplicativos/sei-playwright
    node dist/api.js

    # Depois rode este script
    python example_usage.py
"""

import asyncio
import os
from sei_chatbot import SEIChatbot


def get_available_providers() -> dict:
    """Verifica quais providers estão configurados"""
    providers = {}

    if os.getenv("OPENAI_API_KEY"):
        providers["openai"] = os.getenv("OPENAI_API_KEY")

    if os.getenv("ANTHROPIC_API_KEY"):
        providers["anthropic"] = os.getenv("ANTHROPIC_API_KEY")

    if os.getenv("GOOGLE_API_KEY"):
        providers["google"] = os.getenv("GOOGLE_API_KEY")

    return providers


async def main():
    # Verificar providers disponíveis
    available = get_available_providers()

    if not available:
        print("Nenhuma API key configurada!")
        print("Configure pelo menos uma das variáveis:")
        print("  - OPENAI_API_KEY")
        print("  - ANTHROPIC_API_KEY")
        print("  - GOOGLE_API_KEY")
        return

    print("=" * 60)
    print("SEI Chatbot - Exemplo de Uso Multi-Provider")
    print("=" * 60)
    print("\nProviders disponíveis:")

    provider_list = list(available.keys())
    for i, p in enumerate(provider_list, 1):
        print(f"  {i}. {p}")

    # Selecionar provider
    choice = input(f"\nEscolha o provider (1-{len(provider_list)}): ").strip()
    try:
        provider = provider_list[int(choice) - 1]
    except (ValueError, IndexError):
        provider = provider_list[0]
        print(f"Usando provider padrão: {provider}")

    # Criar chatbot
    chatbot = SEIChatbot(
        sei_api_url=os.getenv("SEI_API_URL", "http://localhost:3001"),
        sei_api_key=os.getenv("SEI_API_KEY", ""),
        provider=provider,
        api_key=available[provider]
    )

    user_id = "teste123"

    print(f"\n[{provider.upper()}] Chatbot iniciado!")
    print("Digite suas mensagens (ou 'sair' para encerrar):\n")

    while True:
        try:
            message = input("Você: ").strip()

            if not message:
                continue

            if message.lower() in ["sair", "exit", "quit"]:
                print("\nEncerrando...")
                break

            if message.lower() == "trocar":
                print("\nProviders disponíveis:")
                for i, p in enumerate(provider_list, 1):
                    marker = " (atual)" if p == provider else ""
                    print(f"  {i}. {p}{marker}")
                choice = input("Escolha: ").strip()
                try:
                    new_provider = provider_list[int(choice) - 1]
                    if new_provider != provider:
                        provider = new_provider
                        chatbot = SEIChatbot(
                            sei_api_url=os.getenv("SEI_API_URL", "http://localhost:3001"),
                            sei_api_key=os.getenv("SEI_API_KEY", ""),
                            provider=provider,
                            api_key=available[provider]
                        )
                        print(f"\nTrocado para {provider.upper()}")
                except (ValueError, IndexError):
                    print("Opção inválida")
                continue

            response = await chatbot.chat(user_id, message)
            print(f"\n[{provider.upper()}]: {response}\n")

        except KeyboardInterrupt:
            print("\n\nInterrompido pelo usuário.")
            break
        except Exception as e:
            print(f"\nErro: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
