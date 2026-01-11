"""
Diagram Generation Service
Gera diagramas Mermaid via IA
"""

from typing import Dict, Any, Optional
from loguru import logger


class DiagramGeneratorService:
    """Serviço para geração de diagramas Mermaid"""
    
    def __init__(self):
        logger.info("DiagramGeneratorService inicializado")
    
    async def generate_diagram(
        self,
        content: str,
        diagram_type: str = "flowchart",
        custom_instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Gera diagrama Mermaid a partir de conteúdo
        
        Args:
            content: Texto base para gerar o diagrama
            diagram_type: Tipo do diagrama (flowchart, sequence, class, etc)
            custom_instructions: Instruções adicionais para a IA
            
        Returns:
            Dicionário com código Mermaid e metadados
        """
        logger.info(f"Gerando diagrama tipo '{diagram_type}' a partir de {len(content)} caracteres")
        
        try:
            # Construir prompt para IA
            prompt = self._build_diagram_prompt(content, diagram_type, custom_instructions)
            
            # TODO: Chamar IA para gerar diagrama
            # Por enquanto, retornar exemplo simulado
            mermaid_code = self._generate_sample_diagram(diagram_type)
            
            return {
                "success": True,
                "mermaid_code": mermaid_code,
                "diagram_type": diagram_type,
                "estimated_complexity": self._estimate_complexity(mermaid_code),
                "message": "Diagrama gerado com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao gerar diagrama: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Erro ao gerar diagrama"
            }
    
    def _build_diagram_prompt(
        self,
        content: str,
        diagram_type: str,
        custom_instructions: Optional[str] = None
    ) -> str:
        """Constrói prompt para geração do diagrama"""
        
        base_prompt = f"""Baseado no seguinte conteúdo, crie um diagrama {diagram_type} em sintaxe Mermaid:

CONTEÚDO:
{content[:2000]}  # Limitar para não exceder tokens

TIPO DE DIAGRAMA: {diagram_type}
"""
        
        if custom_instructions:
            base_prompt += f"\nINSTRUÇÕES ADICIONAIS: {custom_instructions}\n"
        
        base_prompt += """
REGRAS:
1. Use apenas sintaxe Mermaid válida
2. Seja claro e organize logicamente
3. Use labels descritivos em português
4. Retorne APENAS o código Mermaid (sem explicações)

CÓDIGO MERMAID:
"""
        
        return base_prompt
    
    def _generate_sample_diagram(self, diagram_type: str) -> str:
        """Gera diagrama de exemplo baseado no tipo"""
        
        samples = {
            "flowchart": """flowchart TD
    A[Início] --> B{Decisão}
    B -->|Sim| C[Ação 1]
    B -->|Não| D[Ação 2]
    C --> E[Fim]
    D --> E
""",
            "sequence": """sequenceDiagram
    participant A as Cliente
    participant B as API
    participant C as Banco de Dados
    
    A->>B: Fazer Requisição
    B->>C: Consultar Dados
    C-->>B: Retornar Dados
    B-->>A: Resposta
""",
            "class": """classDiagram
    class Documento {
        +String id
        +String titulo
        +String conteudo
        +processar()
        +salvar()
    }
    class Usuario {
        +String nome
        +String email
        +autenticar()
    }
    Usuario "1" --> "*" Documento : possui
""",
            "gantt": """gantt
    title Cronograma do Projeto
    dateFormat YYYY-MM-DD
    
    section Planejamento
    Análise           :a1, 2024-01-01, 7d
    Design            :a2, after a1, 5d
    
    section Desenvolvimento
    Implementação     :a3, after a2, 14d
    Testes            :a4, after a3, 7d
""",
            "pie": """pie title Distribuição de Tarefas
    "Planejamento" : 20
    "Desenvolvimento" : 50
    "Testes" : 20
    "Documentação" : 10
""",
            "mindmap": """mindmap
    root((Projeto))
        Planejamento
            Requisitos
            Cronograma
        Desenvolvimento
            Backend
            Frontend
        Testes
            Unitários
            Integração
""",
        }
        
        return samples.get(diagram_type, samples["flowchart"])
    
    def _estimate_complexity(self, mermaid_code: str) -> str:
        """Estima complexidade do diagrama"""
        lines = len(mermaid_code.split('\n'))
        
        if lines < 10:
            return "baixa"
        elif lines < 30:
            return "média"
        else:
            return "alta"
    
    def validate_mermaid_syntax(self, mermaid_code: str) -> Dict[str, Any]:
        """
        Valida sintaxe básica do código Mermaid
        
        Returns:
            Dicionário com resultado da validação
        """
        try:
            # Validações básicas
            if not mermaid_code.strip():
                return {
                    "valid": False,
                    "error": "Código vazio"
                }
            
            # Verificar se começa com tipo de diagrama válido
            first_line = mermaid_code.strip().split('\n')[0].strip()
            valid_types = [
                "flowchart", "graph", "sequenceDiagram", "classDiagram",
                "stateDiagram", "erDiagram", "gantt", "pie", "mindmap"
            ]
            
            if not any(first_line.startswith(t) for t in valid_types):
                return {
                    "valid": False,
                    "error": f"Tipo de diagrama inválido. Use um dos seguintes: {', '.join(valid_types)}"
                }
            
            return {
                "valid": True,
                "diagram_type": first_line.split()[0],
                "lines": len(mermaid_code.split('\n'))
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }


# Instância global
diagram_generator_service = DiagramGeneratorService()
