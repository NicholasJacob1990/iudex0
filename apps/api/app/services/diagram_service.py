"""
Serviço de geração de diagramas
Cria visualizações a partir de texto estruturado
"""

import os
import uuid
from typing import Optional
from loguru import logger


class DiagramService:
    """
    Serviço para gerar diagramas
    
    Suporta:
    - Mermaid (via mermaid-cli)
    - PlantUML
    - Graphviz
    """
    
    def __init__(self, storage_path: str = "storage/diagrams"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
    
    async def generate_diagram(
        self,
        content: str,
        diagram_type: str = "mermaid",
        title: Optional[str] = None,
        format: str = "svg"
    ) -> dict:
        """
        Gerar diagrama a partir de texto estruturado
        
        Args:
            content: Conteúdo do diagrama (código Mermaid, PlantUML, etc.)
            diagram_type: Tipo de diagrama (mermaid, plantuml, graphviz)
            title: Título do diagrama
            format: Formato de saída (svg, png, pdf)
            
        Returns:
            Dict com url, type, etc.
        """
        try:
            diagram_id = str(uuid.uuid4())
            filename = f"{diagram_id}.{format}"
            filepath = os.path.join(self.storage_path, filename)
            
            success = False
            
            if diagram_type.lower() == "mermaid":
                success = await self._generate_mermaid(content, filepath, format)
            elif diagram_type.lower() == "plantuml":
                success = await self._generate_plantuml(content, filepath, format)
            elif diagram_type.lower() == "graphviz":
                success = await self._generate_graphviz(content, filepath, format)
            
            if success:
                return {
                    "id": diagram_id,
                    "title": title or "Diagrama Gerado",
                    "url": f"/diagrams/{filename}",
                    "filepath": filepath,
                    "type": diagram_type,
                    "format": format,
                    "status": "ready"
                }
            else:
                # Retornar referência ao código para renderizar no frontend
                return {
                    "id": diagram_id,
                    "title": title or "Diagrama",
                    "code": content,
                    "type": diagram_type,
                    "status": "client_render",
                    "message": "Renderize no frontend usando mermaid.js"
                }
                
        except Exception as e:
            logger.error(f"Erro ao gerar diagrama: {e}")
            return {
                "error": str(e),
                "status": "error"
            }
    
    async def _generate_mermaid(
        self,
        content: str,
        filepath: str,
        format: str
    ) -> bool:
        """
        Gerar diagrama Mermaid usando mermaid-cli
        """
        try:
            import subprocess
            import tempfile
            
            # Criar arquivo temporário com código Mermaid
            with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False) as f:
                f.write(content)
                temp_path = f.name
            
            # Executar mermaid-cli
            cmd = [
                'mmdc',  # mermaid-cli command
                '-i', temp_path,
                '-o', filepath,
                '-b', 'transparent'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Limpar arquivo temporário
            os.unlink(temp_path)
            
            if result.returncode == 0:
                logger.info(f"Diagrama Mermaid gerado: {filepath}")
                return True
            else:
                logger.warning(f"mermaid-cli falhou: {result.stderr}")
                return False
                
        except FileNotFoundError:
            logger.warning("mermaid-cli (mmdc) não encontrado. Instale com: npm install -g @mermaid-js/mermaid-cli")
            return False
        except Exception as e:
            logger.error(f"Erro ao gerar Mermaid: {e}")
            return False
    
    async def _generate_plantuml(
        self,
        content: str,
        filepath: str,
        format: str
    ) -> bool:
        """
        Gerar diagrama PlantUML
        """
        try:
            import subprocess
            import tempfile
            
            # Criar arquivo temporário
            with tempfile.NamedTemporaryFile(mode='w', suffix='.puml', delete=False) as f:
                f.write(content)
                temp_path = f.name
            
            # Executar PlantUML
            cmd = ['plantuml', temp_path, f'-t{format}', '-o', os.path.dirname(filepath)]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            os.unlink(temp_path)
            
            if result.returncode == 0:
                logger.info(f"Diagrama PlantUML gerado: {filepath}")
                return True
            else:
                logger.warning(f"PlantUML falhou: {result.stderr}")
                return False
                
        except FileNotFoundError:
            logger.warning("PlantUML não encontrado")
            return False
        except Exception as e:
            logger.error(f"Erro ao gerar PlantUML: {e}")
            return False
    
    async def _generate_graphviz(
        self,
        content: str,
        filepath: str,
        format: str
    ) -> bool:
        """
        Gerar diagrama Graphviz
        """
        try:
            import subprocess
            import tempfile
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
                f.write(content)
                temp_path = f.name
            
            # Executar Graphviz (dot)
            cmd = ['dot', f'-T{format}', temp_path, '-o', filepath]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            os.unlink(temp_path)
            
            if result.returncode == 0:
                logger.info(f"Diagrama Graphviz gerado: {filepath}")
                return True
            else:
                logger.warning(f"Graphviz falhou: {result.stderr}")
                return False
                
        except FileNotFoundError:
            logger.warning("Graphviz não encontrado")
            return False
        except Exception as e:
            logger.error(f"Erro ao gerar Graphviz: {e}")
            return False
    
    def generate_mermaid_from_text(self, text: str, diagram_type: str = "flowchart") -> str:
        """
        Gerar código Mermaid a partir de texto usando IA
        
        Args:
            text: Descrição do processo/fluxo
            diagram_type: Tipo de diagrama (flowchart, sequence, gantt, etc.)
            
        Returns:
            Código Mermaid gerado
        """
        # TODO: Usar IA (Claude, GPT) para converter texto em código Mermaid
        # Por enquanto, retornar template básico
        
        if diagram_type == "flowchart":
            return f"""flowchart TD
    A[Início] --> B[{text[:30]}...]
    B --> C[Processamento]
    C --> D[Fim]
"""
        elif diagram_type == "sequence":
            return f"""sequenceDiagram
    participant A as Usuário
    participant B as Sistema
    A->>B: {text[:30]}
    B-->>A: Resposta
"""
        else:
            return f"""graph TD
    A[{text[:30]}]
"""


# Instância global
diagram_service = DiagramService()
