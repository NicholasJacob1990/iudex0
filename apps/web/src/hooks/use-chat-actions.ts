'use client';

import { useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useChatStore, useCanvasStore } from '@/stores';
import { toast } from 'sonner';

/**
 * Chat action handlers: send, share, export, generate, new chat.
 */
export function useChatActions(basePath: string) {
  const router = useRouter();
  const {
    currentChat,
    createChat,
    setCurrentChat,
    sendMessage,
    startAgentGeneration,
    chatMode,
    setChatMode,
    selectedModels,
    setSelectedModels,
    setShowMultiModelComparator,
  } = useChatStore();

  const {
    showCanvas,
    setState: setCanvasState,
    setActiveTab,
  } = useCanvasStore();

  const activeChatId = currentChat?.id || null;

  const DEFAULT_COMPARE_MODELS = ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-flash'];

  // --- Set chat mode (standard / multi-model) ---
  const handleSetChatMode = (next: 'standard' | 'multi-model') => {
    if (next === 'multi-model') {
      const nextModels =
        selectedModels.length >= 2
          ? selectedModels
          : selectedModels.length === 1
            ? [
                selectedModels[0],
                DEFAULT_COMPARE_MODELS.find((m) => m !== selectedModels[0]) || 'gpt-5.2',
              ]
            : DEFAULT_COMPARE_MODELS.slice(0, 3);

      setSelectedModels(nextModels);
      setShowMultiModelComparator(true);
      setChatMode('multi-model');
      return;
    }

    if (selectedModels.length > 1) setSelectedModels([selectedModels[0]]);
    setChatMode('standard');
  };

  // --- Start new chat ---
  const handleStartNewChat = async () => {
    try {
      const newChat = await createChat();
      toast.success('Nova conversa criada!');
      if (newChat?.id) {
        router.push(`${basePath}/${newChat.id}`);
      }
    } catch {
      toast.error('Erro ao criar conversa');
    }
  };

  // --- Generate (agent) ---
  const handleGenerate = async () => {
    try {
      let chat = currentChat;
      if (!chat && activeChatId) {
        await setCurrentChat(activeChatId);
        chat = useChatStore.getState().currentChat;
      }
      if (!chat) {
        chat = await createChat();
      }
      await startAgentGeneration('Gerar minuta baseada nos documentos selecionados.');
    } catch {
      // handled by store/toast
    }
  };

  // --- Open quality panel ---
  const handleOpenQuality = () => {
    showCanvas();
    setActiveTab('audit');
  };

  // --- Message sent (auto-open canvas for drafts) ---
  const handleMessageSent = useCallback(
    (content: string) => {
      const draftKeywords = [
        'redija', 'escreva', 'elabore', 'minuta', 'peticao', 'parecer',
        'draft', 'write', 'memo', 'memorando', 'contrato', 'acordo',
      ];

      const shouldOpenCanvas = draftKeywords.some((keyword) =>
        content.toLowerCase().includes(keyword),
      );

      if (shouldOpenCanvas) {
        showCanvas();
        setCanvasState('normal');
      }
    },
    [showCanvas, setCanvasState],
  );

  // --- Send message ---
  const handleSend = useCallback(
    async (content: string) => {
      handleMessageSent(content);

      if (!currentChat) {
        try {
          await createChat();
        } catch {
          toast.error('Erro ao criar conversa');
          return;
        }
      }

      sendMessage(content);
    },
    [handleMessageSent, sendMessage, currentChat, createChat],
  );

  // --- Export conversation ---
  const formatConversationForExport = useCallback(() => {
    const messages = currentChat?.messages || [];
    return messages
      .map((m) => {
        const role = m.role === 'user' ? 'Usuario' : 'Iudex';
        const time = new Date(m.timestamp).toLocaleString('pt-BR');
        return `[${time}] ${role}\n${m.content}\n`;
      })
      .join('\n----------------------------------------\n');
  }, [currentChat?.messages]);

  const handleShareChat = useCallback(async () => {
    if (!currentChat?.messages?.length) {
      toast.error('Nada para compartilhar.');
      return;
    }

    const shareUrl =
      typeof window !== 'undefined'
        ? window.location.href
        : `${basePath}/${activeChatId || currentChat.id}`;

    const shareText = String(currentChat.messages[currentChat.messages.length - 1]?.content || '')
      .trim()
      .slice(0, 300);

    try {
      if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
        await navigator.share({
          title: 'Conversa Iudex',
          text: shareText || 'Conversa jurídica no Iudex',
          url: shareUrl,
        });
        return;
      }
    } catch (error) {
      if ((error as Error)?.name === 'AbortError') {
        return;
      }
    }

    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareUrl);
      } else if (typeof document !== 'undefined') {
        const textarea = document.createElement('textarea');
        textarea.value = shareUrl;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      toast.success('Link copiado para a area de transferencia.');
    } catch {
      toast.error('Nao foi possivel compartilhar.');
    }
  }, [activeChatId, basePath, currentChat]);

  const handleExportChat = useCallback(async () => {
    if (!currentChat?.messages?.length) {
      toast.error('Nada para exportar.');
      return;
    }

    const markdown = formatConversationForExport();
    const fileBase = activeChatId || currentChat.id || 'chat';
    const filename = `chat-${String(fileBase).slice(0, 8)}.md`;

    try {
      if (typeof window !== 'undefined') {
        const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        toast.success('Export concluido (.md).');
        return;
      }
    } catch {
      // fallback below
    }

    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(markdown);
        toast.success('Conteudo copiado para a area de transferencia.');
        return;
      }
    } catch {
      // noop
    }

    toast.error('Nao foi possivel exportar o chat.');
  }, [activeChatId, currentChat, formatConversationForExport]);

  return {
    // Chat store pass-through
    currentChat,
    createChat,
    setCurrentChat,
    sendMessage,
    startAgentGeneration,
    chatMode,
    setChatMode,
    selectedModels,
    setSelectedModels,
    setShowMultiModelComparator,

    // Router
    router,
    activeChatId,

    // Model defaults
    DEFAULT_COMPARE_MODELS,

    // Handlers
    handleSetChatMode,
    handleStartNewChat,
    handleGenerate,
    handleOpenQuality,
    handleMessageSent,
    handleSend,
    handleShareChat,
    handleExportChat,
  };
}
