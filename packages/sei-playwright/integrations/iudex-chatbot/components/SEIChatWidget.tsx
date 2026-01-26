/**
 * SEI Chat Widget para Iudex
 * Componente React que fornece UI de chatbot para automação do SEI
 * Suporta GPT, Claude e Gemini
 *
 * Uso:
 *   import { SEIChatWidget } from '@/components/sei-chat/SEIChatWidget'
 *   <SEIChatWidget userId="user123" apiUrl="/api/sei-chat" />
 */

'use client';

import { useState, useRef, useEffect, useCallback } from 'react';

type Provider = 'openai' | 'anthropic' | 'google';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  provider?: Provider;
}

interface ProviderInfo {
  name: Provider;
  available: boolean;
  default_model: string;
}

interface SEIChatWidgetProps {
  userId: string;
  apiUrl?: string;
  placeholder?: string;
  title?: string;
  defaultProvider?: Provider;
  onSessionChange?: (active: boolean) => void;
  onProviderChange?: (provider: Provider) => void;
}

const PROVIDER_LABELS: Record<Provider, { name: string; icon: string }> = {
  openai: { name: 'GPT-4o', icon: '🟢' },
  anthropic: { name: 'Claude', icon: '🟠' },
  google: { name: 'Gemini', icon: '🔵' },
};

export function SEIChatWidget({
  userId,
  apiUrl = '/api/sei-chat',
  placeholder = 'Digite uma mensagem ou comando SEI...',
  title = 'Assistente SEI',
  defaultProvider = 'openai',
  onSessionChange,
  onProviderChange,
}: SEIChatWidgetProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionActive, setSessionActive] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [provider, setProvider] = useState<Provider>(defaultProvider);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [showProviderSelect, setShowProviderSelect] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Scroll para última mensagem
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Carregar providers disponíveis
  useEffect(() => {
    loadProviders();
  }, []);

  // Verificar sessão ao montar ou trocar provider
  useEffect(() => {
    checkSession();
  }, [userId, provider]);

  // Notificar mudanças
  useEffect(() => {
    onSessionChange?.(sessionActive);
  }, [sessionActive, onSessionChange]);

  useEffect(() => {
    onProviderChange?.(provider);
  }, [provider, onProviderChange]);

  const loadProviders = async () => {
    try {
      const res = await fetch(`${apiUrl}/providers`);
      const data = await res.json();
      setProviders(data.providers);
      if (data.default && !defaultProvider) {
        setProvider(data.default);
      }
    } catch (error) {
      console.error('Erro ao carregar providers:', error);
    }
  };

  const checkSession = async () => {
    try {
      const res = await fetch(`${apiUrl}/session/${userId}?provider=${provider}`);
      const data = await res.json();
      setSessionActive(data.active);
    } catch (error) {
      console.error('Erro ao verificar sessão:', error);
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await fetch(`${apiUrl}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          message: input,
          provider: provider,
        }),
      });

      const data = await res.json();

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.response || data.detail || 'Erro ao processar mensagem',
        timestamp: new Date(),
        provider: data.provider,
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setSessionActive(data.session_active ?? sessionActive);
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Erro de conexão. Tente novamente.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const clearHistory = async () => {
    try {
      await fetch(`${apiUrl}/history/${userId}?provider=${provider}`, { method: 'DELETE' });
      setMessages([]);
    } catch (error) {
      console.error('Erro ao limpar histórico:', error);
    }
  };

  const logout = async () => {
    try {
      await fetch(`${apiUrl}/logout/${userId}?provider=${provider}`, { method: 'POST' });
      setSessionActive(false);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: 'assistant',
          content: 'Sessão encerrada com sucesso.',
          timestamp: new Date(),
        },
      ]);
    } catch (error) {
      console.error('Erro ao fazer logout:', error);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleProviderChange = (newProvider: Provider) => {
    setProvider(newProvider);
    setShowProviderSelect(false);
    // Limpar histórico ao trocar provider (contexto diferente)
    setMessages([]);
  };

  // Sugestões de comandos
  const suggestions = [
    'Faça login no SEI',
    'Liste os tipos de processo',
    'Crie um processo de comunicação interna',
  ];

  const currentProviderInfo = PROVIDER_LABELS[provider];
  const availableProviders = providers.filter((p) => p.available);

  return (
    <>
      {/* Botão flutuante */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-4 right-4 w-14 h-14 bg-blue-600 hover:bg-blue-700 text-white rounded-full shadow-lg flex items-center justify-center transition-all z-50"
        aria-label="Abrir chat SEI"
      >
        {isOpen ? (
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
        )}
        {sessionActive && (
          <span className="absolute top-0 right-0 w-3 h-3 bg-green-500 rounded-full border-2 border-white" />
        )}
      </button>

      {/* Widget de chat */}
      {isOpen && (
        <div className="fixed bottom-20 right-4 w-96 h-[500px] bg-white dark:bg-gray-800 rounded-lg shadow-2xl flex flex-col z-50 border border-gray-200 dark:border-gray-700">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-blue-600 text-white rounded-t-lg">
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span className="font-medium">{title}</span>
              {sessionActive && (
                <span className="text-xs bg-green-500 px-2 py-0.5 rounded-full">Conectado</span>
              )}
            </div>
            <div className="flex items-center gap-1">
              {sessionActive && (
                <button
                  onClick={logout}
                  className="p-1.5 hover:bg-blue-700 rounded transition-colors"
                  title="Desconectar"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                  </svg>
                </button>
              )}
              <button
                onClick={clearHistory}
                className="p-1.5 hover:bg-blue-700 rounded transition-colors"
                title="Limpar histórico"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>

          {/* Provider selector */}
          <div className="px-4 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-750">
            <div className="relative">
              <button
                onClick={() => setShowProviderSelect(!showProviderSelect)}
                className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
              >
                <span>{currentProviderInfo.icon}</span>
                <span>{currentProviderInfo.name}</span>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {showProviderSelect && availableProviders.length > 1 && (
                <div className="absolute top-full left-0 mt-1 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1 z-10">
                  {availableProviders.map((p) => (
                    <button
                      key={p.name}
                      onClick={() => handleProviderChange(p.name)}
                      className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 hover:bg-gray-100 dark:hover:bg-gray-700 ${
                        p.name === provider ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                      }`}
                    >
                      <span>{PROVIDER_LABELS[p.name].icon}</span>
                      <span>{PROVIDER_LABELS[p.name].name}</span>
                      <span className="text-xs text-gray-400 ml-auto">{p.default_model}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Mensagens */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && (
              <div className="text-center text-gray-500 dark:text-gray-400 py-8">
                <p className="mb-4">Como posso ajudar com o SEI?</p>
                <div className="space-y-2">
                  {suggestions.map((suggestion, i) => (
                    <button
                      key={i}
                      onClick={() => setInput(suggestion)}
                      className="block w-full text-sm text-left px-3 py-2 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] px-4 py-2 rounded-lg ${
                    message.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100'
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs opacity-60">
                      {message.timestamp.toLocaleTimeString('pt-BR', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                    {message.provider && message.role === 'assistant' && (
                      <span className="text-xs opacity-60">
                        {PROVIDER_LABELS[message.provider]?.icon}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-gray-100 dark:bg-gray-700 px-4 py-2 rounded-lg">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">{currentProviderInfo.icon}</span>
                    <div className="flex space-x-1">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-4 border-t border-gray-200 dark:border-gray-700">
            <div className="flex gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder={placeholder}
                disabled={isLoading}
                className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white disabled:opacity-50"
              />
              <button
                onClick={sendMessage}
                disabled={isLoading || !input.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default SEIChatWidget;
