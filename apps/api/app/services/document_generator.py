"""
Serviço de Geração de Documentos com Assinatura
Integra IA multi-agente com templates e dados do usuário
"""

from typing import Dict, Any, Optional, List
import uuid
from datetime import datetime
from loguru import logger
import re

from app.services.ai.orchestrator import MultiAgentOrchestrator
from app.models.user import User
from app.schemas.document import DocumentGenerationRequest, DocumentGenerationResponse


class DocumentGenerator:
    """
    Serviço que gera documentos jurídicos usando IA e templates,
    incluindo dados de assinatura do usuário
    """
    
    def __init__(self):
        self.orchestrator = MultiAgentOrchestrator()
        logger.info("DocumentGenerator inicializado")
    
    async def generate_document(
        self,
        request: DocumentGenerationRequest,
        user: User,
        context_data: Optional[Dict[str, Any]] = None
    ) -> DocumentGenerationResponse:
        """
        Gera documento completo com assinatura
        
        Args:
            request: Dados da requisição de geração
            user: Usuário que está gerando o documento
            context_data: Dados de contexto adicionais (documentos, etc.)
        
        Returns:
            Resposta com documento gerado
        """
        logger.info(f"Gerando documento para usuário {user.id}, tipo: {request.document_type}")
        
        # Preparar contexto completo
        context = self._prepare_context(request, user, context_data)
        
        # Preparar prompt com informações do usuário
        enhanced_prompt = self._enhance_prompt_with_user_data(
            request.prompt,
            user,
            request.document_type
        )
        
        # Gerar documento usando multi-agente
        result = await self.orchestrator.generate_document(
            prompt=enhanced_prompt,
            context=context,
            effort_level=request.effort_level
        )
        
        # Processar conteúdo gerado
        content = result.final_content
        
        # Aplicar template se fornecido
        if request.template_id:
            content = await self._apply_template(
                content,
                request.template_id,
                request.variables,
                user
            )
        
        # Adicionar assinatura se solicitado
        signature_data = None
        if request.include_signature:
            content, signature_data = self._add_signature(content, user)
        
        # Converter para HTML
        content_html = self._markdown_to_html(content)
        
        # Calcular estatísticas
        statistics = self._calculate_statistics(content)
        
        # Preparar informações de custo
        cost_info = {
            "total_tokens": result.total_tokens,
            "total_cost": result.total_cost,
            "processing_time": result.processing_time_seconds,
            "agents_used": result.metadata.get("agents_used", []),
            "effort_level": request.effort_level
        }
        
        # Criar documento ID
        document_id = str(uuid.uuid4())
        
        logger.info(f"Documento gerado com sucesso: {document_id}")
        
        return DocumentGenerationResponse(
            document_id=document_id,
            content=content,
            content_html=content_html,
            metadata={
                "document_type": request.document_type,
                "language": request.language,
                "tone": request.tone,
                "template_id": request.template_id,
                "user_id": user.id,
                "user_account_type": user.account_type.value,
                "generated_at": datetime.utcnow().isoformat(),
                "reviews": [
                    {
                        "agent": review.agent_name,
                        "score": review.score,
                        "approved": review.approved
                    }
                    for review in result.reviews
                ],
                "consensus": result.consensus,
                "conflicts": result.conflicts
            },
            statistics=statistics,
            cost_info=cost_info,
            signature_data=signature_data
        )
    
    def _prepare_context(
        self,
        request: DocumentGenerationRequest,
        user: User,
        context_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Prepara contexto completo para geração"""
        context = {
            "document_type": request.document_type,
            "language": request.language,
            "tone": request.tone,
            "user_info": {
                "account_type": user.account_type.value,
                "name": user.name,
                "email": user.email,
            },
            "variables": request.variables,
            "max_length": request.max_length
        }
        
        # Adicionar dados específicos do tipo de conta
        if user.account_type.value == "INDIVIDUAL":
            context["user_info"].update({
                "oab": user.oab,
                "oab_state": user.oab_state,
                "cpf": user.cpf,
                "phone": user.phone
            })
        else:
            context["user_info"].update({
                "institution_name": user.institution_name,
                "cnpj": user.cnpj,
                "position": user.position,
                "department": user.department,
                "institution_address": user.institution_address,
                "institution_phone": user.institution_phone
            })
        
        # Adicionar contexto adicional se fornecido
        if context_data:
            context.update(context_data)
        
        return context
    
    def _enhance_prompt_with_user_data(
        self,
        prompt: str,
        user: User,
        document_type: str
    ) -> str:
        """Aprimora o prompt com informações contextuais do usuário"""
        
        user_context = f"\n\n--- INFORMAÇÕES DO AUTOR ---\n"
        user_context += f"Nome: {user.name}\n"
        
        if user.account_type.value == "INDIVIDUAL":
            if user.oab and user.oab_state:
                user_context += f"OAB: {user.oab}/{user.oab_state}\n"
        else:
            user_context += f"Instituição: {user.institution_name}\n"
            if user.position:
                user_context += f"Cargo: {user.position}\n"
        
        user_context += f"\n--- TIPO DE DOCUMENTO ---\n{document_type}\n"
        user_context += f"\n--- REQUISIÇÃO ---\n{prompt}\n"
        
        return user_context
    
    async def _apply_template(
        self,
        content: str,
        template_id: str,
        variables: Dict[str, Any],
        user: User
    ) -> str:
        """Aplica template ao conteúdo"""
        # TODO: Buscar template do banco de dados
        # Por enquanto, apenas substitui variáveis básicas
        
        # Substituir variáveis do template
        for key, value in variables.items():
            content = content.replace(f"{{{{{key}}}}}", str(value))
        
        # Substituir variáveis automáticas do usuário
        user_vars = {
            "user_name": user.name,
            "user_email": user.email,
            "user_oab": f"{user.oab}/{user.oab_state}" if user.oab else "",
            "user_institution": user.institution_name or "",
            "user_position": user.position or "",
            "user_cnpj": user.cnpj or "",
            "date": datetime.now().strftime("%d/%m/%Y"),
            "datetime": datetime.now().strftime("%d/%m/%Y %H:%M")
        }
        
        for key, value in user_vars.items():
            content = content.replace(f"{{{{{key}}}}}", str(value))
        
        return content
    
    def _add_signature(self, content: str, user: User) -> tuple[str, Dict[str, Any]]:
        """Adiciona assinatura ao documento"""
        
        signature_data = user.full_signature_data
        
        # Criar bloco de assinatura
        signature_block = "\n\n---\n\n"
        
        if user.account_type.value == "INDIVIDUAL":
            signature_block += f"**{user.name}**\n"
            if user.oab and user.oab_state:
                signature_block += f"OAB/{user.oab_state} {user.oab}\n"
            if user.cpf:
                signature_block += f"CPF: {self._format_cpf(user.cpf)}\n"
            if user.email:
                signature_block += f"Email: {user.email}\n"
            if user.phone:
                signature_block += f"Tel: {user.phone}\n"
        else:
            signature_block += f"**{user.name}**\n"
            if user.position:
                signature_block += f"{user.position}\n"
            if user.department:
                signature_block += f"{user.department}\n"
            if user.institution_name:
                signature_block += f"{user.institution_name}\n"
            if user.cnpj:
                signature_block += f"CNPJ: {self._format_cnpj(user.cnpj)}\n"
            if user.institution_address:
                signature_block += f"{user.institution_address}\n"
            if user.email:
                signature_block += f"Email: {user.email}\n"
            if user.institution_phone:
                signature_block += f"Tel: {user.institution_phone}\n"
        
        # Adicionar imagem de assinatura se disponível
        if user.signature_image:
            signature_block += f"\n![Assinatura]({user.signature_image})\n"
        
        content_with_signature = content + signature_block
        
        return content_with_signature, signature_data
    
    def _markdown_to_html(self, markdown: str) -> str:
        """Converte markdown para HTML"""
        # Conversão básica de markdown
        # Em produção, use uma biblioteca como python-markdown
        
        html = markdown
        
        # Headers
        html = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        
        # Bold
        html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
        
        # Italic
        html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
        
        # Links
        html = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', html)
        
        # Images
        html = re.sub(r'!\[(.*?)\]\((.*?)\)', r'<img src="\2" alt="\1" />', html)
        
        # Paragraphs
        html = re.sub(r'\n\n', '</p><p>', html)
        html = f'<p>{html}</p>'
        
        # Line breaks
        html = html.replace('\n', '<br />')
        
        return html
    
    def _calculate_statistics(self, content: str) -> Dict[str, Any]:
        """Calcula estatísticas do documento"""
        words = len(content.split())
        chars = len(content)
        chars_no_spaces = len(content.replace(" ", ""))
        lines = len(content.split("\n"))
        paragraphs = len([p for p in content.split("\n\n") if p.strip()])
        
        return {
            "words": words,
            "characters": chars,
            "characters_no_spaces": chars_no_spaces,
            "lines": lines,
            "paragraphs": paragraphs,
            "estimated_pages": max(1, words // 250)  # ~250 palavras por página
        }
    
    def _format_cpf(self, cpf: str) -> str:
        """Formata CPF"""
        if len(cpf) == 11:
            return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
        return cpf
    
    def _format_cnpj(self, cnpj: str) -> str:
        """Formata CNPJ"""
        if len(cnpj) == 14:
            return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
        return cnpj

