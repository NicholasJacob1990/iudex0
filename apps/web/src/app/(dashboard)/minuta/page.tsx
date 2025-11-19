'use client';

import { useState } from 'react';
import { useChatStore } from '@/stores';
import { Button } from '@/components/ui/button';
import { ChatInterface } from '@/components/chat';
import { Sparkles, FileText } from 'lucide-react';
import { toast } from 'sonner';
import { minuteHistory } from '@/data/mock';
import { MinuteHistoryGrid, DocumentCanvas, ContextPanel } from '@/components/dashboard';

export default function MinutaPage() {
  const { currentChat, createChat, generateDocument, isSending } = useChatStore();
  const [generatedContent, setGeneratedContent] = useState('');
  const [effortLevel, setEffortLevel] = useState(3);
  const [viewMode, setViewMode] = useState<'chat' | 'minuta'>('chat');

  const handleStartNewMinuta = async () => {
    try {
      await createChat('Nova Minuta');
      toast.success('Nova conversa criada!');
    } catch (error) {
      // handled
    }
  };

  const handleGenerate = async () => {
    if (!currentChat) {
      toast.error('Crie uma conversa primeiro');
      return;
    }

    try {
      const result = await generateDocument({
        prompt: 'Gerar minuta baseada nas informações fornecidas',
        effort_level: effortLevel,
        document_type: 'minuta',
      });

      setGeneratedContent(result.content);
      // Switch to minuta view automatically after generation
      setViewMode('minuta');
      toast.success('Minuta gerada com sucesso!');
    } catch (error) {
      // erros tratados no interceptor
    }
  };

  return (
    <div className="flex h-[calc(100vh-6rem)] flex-col gap-6">
      <div className="flex flex-none flex-col gap-4 rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-muted-foreground">Minuta</p>
          <h1 className="font-display text-3xl text-foreground">Crie documentos impecáveis.</h1>
          <p className="text-sm text-muted-foreground">
            IA multi-agente com janelas ilimitadas, revisão cruzada e contexto amplo.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button variant="ghost" className="rounded-full border border-outline/50" onClick={handleStartNewMinuta}>
            <FileText className="mr-2 h-4 w-4" />
            Nova conversa
          </Button>
          <Button className="rounded-full bg-primary text-primary-foreground" onClick={handleGenerate} disabled={!currentChat || isSending}>
            <Sparkles className="mr-2 h-4 w-4" />
            Gerar minuta
          </Button>
        </div>
      </div>

      <div className="flex flex-1 gap-6 overflow-hidden">
        {/* Left Panel - History & Context (Hidden on mobile, scrollable) */}
        <div className="hidden w-[360px] flex-col gap-6 overflow-y-auto pb-4 lg:flex">
          <ContextPanel />
          <MinuteHistoryGrid items={minuteHistory} />

          <div className="rounded-3xl border border-white/70 bg-white/90 p-5 shadow-soft">
            <h3 className="font-display text-lg text-foreground">Sistema Multi-Agente</h3>
            <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
              <li>• Claude Sonnet 4.5 — geração principal em janela ilimitada</li>
              <li>• Gemini 2.5 Pro — revisão jurídica e aderência normativa</li>
              <li>• GPT-5 — revisão textual, concisão e estilo</li>
            </ul>
          </div>
        </div>

        {/* Main Content Area (Chat or Canvas) */}
        <div className="flex flex-1 flex-col gap-4 overflow-hidden">
          <div className="flex flex-none items-center justify-between rounded-[36px] border border-white/70 bg-white/95 p-4 shadow-soft">
            <div className="flex items-center gap-2 rounded-full border border-outline/50 bg-sand px-3 py-1 text-xs font-semibold uppercase text-muted-foreground">
              <span>Modos</span>
              <button
                type="button"
                className={`rounded-full px-3 py-1 transition-all ${viewMode === 'chat' ? 'bg-primary text-primary-foreground' : 'hover:bg-white'}`}
                onClick={() => setViewMode('chat')}
              >
                Chat
              </button>
              <button
                type="button"
                className={`rounded-full px-3 py-1 transition-all ${viewMode === 'minuta' ? 'bg-primary text-primary-foreground' : 'hover:bg-white'}`}
                onClick={() => setViewMode('minuta')}
              >
                Minuta
              </button>
            </div>
            <div className="flex items-center gap-3 text-xs font-semibold">
              <span className="chip bg-white text-foreground shadow-sm">
                Tokens <strong className="ml-1 text-primary">∞</strong>
              </span>
              <select
                value={effortLevel}
                onChange={(e) => setEffortLevel(Number(e.target.value))}
                className="rounded-full border border-outline/50 bg-white px-3 py-1 text-xs focus:border-primary focus:outline-none"
              >
                {[1, 2, 3, 4, 5].map((level) => (
                  <option key={level} value={level}>
                    Esforço {level}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex-1 overflow-hidden rounded-[36px] border border-white/70 bg-white/95 shadow-soft transition-all duration-300">
            {viewMode === 'chat' ? (
              <div className="flex h-full flex-col">
                <div className="flex-none border-b border-outline/40 px-6 py-4">
                  <p className="font-display text-lg text-foreground">Chat em Tela Cheia</p>
                  <p className="text-sm text-muted-foreground">
                    Conduza a conversa com a IA em modo expandido.
                  </p>
                </div>
                <div className="flex-1 overflow-hidden bg-sand/40 p-4">
                  {currentChat ? (
                    <ChatInterface chatId={currentChat.id} />
                  ) : (
                    <div className="flex h-full flex-col items-center justify-center gap-4 text-muted-foreground">
                      <div className="rounded-full bg-sand p-6">
                        <Sparkles className="h-12 w-12 text-primary/40" />
                      </div>
                      <div className="text-center">
                        <p className="text-lg font-medium text-foreground">Pronto para começar?</p>
                        <p className="text-sm">Inicie uma nova conversa ou selecione uma do histórico.</p>
                      </div>
                      <Button onClick={handleStartNewMinuta} variant="outline" className="mt-2 rounded-full">
                        Criar Conversa
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex h-full flex-col">
                <div className="flex-none border-b border-outline/40 px-6 py-4">
                  <p className="font-display text-lg text-foreground">Canvas Ilimitado</p>
                  <p className="text-sm text-muted-foreground">
                    Visualize o documento sem limite de páginas ou tokens.
                  </p>
                </div>
                <div className="flex-1 overflow-hidden p-0">
                  <DocumentCanvas content={generatedContent} />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
