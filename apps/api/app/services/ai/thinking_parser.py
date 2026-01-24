"""
Thinking Parser - Handles thinking extraction for models using XML parsing approach

For models that don't have native thinking API support (GPT-5.2, Claude Opus, Grok),
we use XML tags (<thinking>...</thinking>) in the prompt and parse the response.
"""

import re
from typing import Tuple, AsyncGenerator, Optional
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# SYSTEM PROMPT INJECTION
# =============================================================================

THINKING_PROMPT_INJECTION = """

IMPORTANTE - PROCESSO DE RACIOCINIO:
Antes de fornecer sua resposta final, voce DEVE pensar passo a passo.
Escreva seu raciocinio em portugues e envolva tudo entre as tags XML <thinking>...</thinking>.
Somente depois de fechar </thinking>, forneca a resposta final ao usuario.

Formato de exemplo:
<thinking>
1. Primeiro, preciso entender...
2. As consideracoes principais sao...
3. Com base nessa analise...
</thinking>

[Sua resposta final aqui]
"""

THINKING_PROMPT_INJECTION_BRIEF = """

IMPORTANTE: Antes de responder, pense brevemente em portugues dentro das tags <thinking>...</thinking>.
Depois de </thinking>, escreva sua resposta final.
"""


def inject_thinking_prompt(
    system_instruction: str,
    brief: bool = False,
    budget_tokens: Optional[int] = None,
) -> str:
    """Inject thinking instructions into the system prompt.
    
    Args:
        system_instruction: The original system instruction
        brief: If True, use a shorter prompt (for lighter models)
    
    Returns:
        Modified system instruction with thinking instructions
    """
    injection = THINKING_PROMPT_INJECTION_BRIEF if brief else THINKING_PROMPT_INJECTION
    if budget_tokens is not None:
        try:
            budget_value = int(budget_tokens)
        except (TypeError, ValueError):
            budget_value = None
        if budget_value is not None and budget_value > 0:
            injection = f"{injection}\nMantenha seu raciocinio abaixo de {budget_value} tokens."
    return system_instruction + injection


# =============================================================================
# STREAMING XML PARSER
# =============================================================================

class ThinkingStreamParser:
    """Stateful parser for extracting <thinking> tags from streaming responses."""
    
    def __init__(self):
        self.buffer = ""
        self.in_thinking = False
        self.thinking_complete = False
    
    def process_token(self, token: str) -> Tuple[Optional[str], Optional[str]]:
        """Process a single token and extract thinking/content.
        
        Args:
            token: The incoming token from the stream
            
        Returns:
            Tuple of (thinking_text, content_text) - one or both may be None
        """
        self.buffer += token
        thinking_text = None
        content_text = None
        
        # Check for opening tag
        if not self.in_thinking and "<thinking>" in self.buffer:
            self.in_thinking = True
            # Extract content before <thinking> tag (if any)
            parts = self.buffer.split("<thinking>", 1)
            if parts[0].strip():
                content_text = parts[0]
            self.buffer = parts[1] if len(parts) > 1 else ""
            return thinking_text, content_text
        
        # Check for closing tag
        if self.in_thinking and "</thinking>" in self.buffer:
            self.in_thinking = False
            self.thinking_complete = True
            # Extract thinking content
            parts = self.buffer.split("</thinking>", 1)
            thinking_text = parts[0]
            self.buffer = parts[1] if len(parts) > 1 else ""
            
            # Check if there's content after the closing tag
            if self.buffer.strip():
                content_text = self.buffer
                self.buffer = ""
            
            return thinking_text, content_text
        
        # If we're in thinking mode, emit thinking content
        if self.in_thinking:
            # Don't emit if we might be at the start of </thinking>
            if "</" in self.buffer or "<" in self.buffer[-20:]:
                # Wait for more content
                return None, None
            thinking_text = self.buffer
            self.buffer = ""
            return thinking_text, None
        
        # If we're done with thinking, emit as content
        if self.thinking_complete:
            content_text = self.buffer
            self.buffer = ""
            return None, content_text
        
        # Still waiting for thinking to start - don't emit yet
        # Only emit if buffer is getting too large
        if len(self.buffer) > 100 and "<" not in self.buffer:
            content_text = self.buffer
            self.buffer = ""
            return None, content_text
        
        return None, None
    
    def flush(self) -> Tuple[Optional[str], Optional[str]]:
        """Flush any remaining content in the buffer.
        
        Returns:
            Tuple of (thinking_text, content_text)
        """
        if not self.buffer:
            return None, None
        
        remaining = self.buffer
        self.buffer = ""
        
        if self.in_thinking:
            return remaining, None
        return None, remaining


async def wrap_stream_with_xml_parsing(
    stream: AsyncGenerator,
    brief: bool = False
) -> AsyncGenerator[Tuple[str, str], None]:
    """Wrap a text stream to extract <thinking> tags.
    
    Args:
        stream: Async generator yielding text tokens
        brief: Whether brief mode was used
        
    Yields:
        Tuples of (chunk_type, content) where chunk_type is 'thinking' or 'text'
    """
    parser = ThinkingStreamParser()
    
    async for token in stream:
        # Handle both tuple and string inputs
        if isinstance(token, tuple):
            token_type, token_text = token
            if token_type == "thinking":
                yield ("thinking", token_text)
                continue
            token = token_text
        
        thinking, content = parser.process_token(token)
        
        if thinking:
            yield ("thinking", thinking)
        if content:
            yield ("text", content)
    
    # Flush remaining content
    thinking, content = parser.flush()
    if thinking:
        yield ("thinking", thinking)
    if content:
        yield ("text", content)
