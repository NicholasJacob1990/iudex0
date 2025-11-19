'use client';

import { useState, KeyboardEvent, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Send, Sparkles, ChevronDown, Paperclip, AtSign, Hash } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface ChatInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [content, setContent] = useState('');
  const [style, setStyle] = useState('Formal');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if (!content.trim() || disabled) return;
    onSend(content);
    setContent('');
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [content]);

  return (
    <div className="relative">
      <div className="group relative flex flex-col gap-2 rounded-xl border border-white/10 bg-white/5 p-2 shadow-sm focus-within:border-indigo-500/50 focus-within:ring-1 focus-within:ring-indigo-500/50 transition-all">
        <textarea
          ref={textareaRef}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Descreva a minuta que você precisa..."
          className="min-h-[60px] w-full resize-none bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
          disabled={disabled}
          rows={1}
        />

        <div className="flex items-center justify-between px-2 pb-1">
          <div className="flex items-center gap-1">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="h-7 gap-1 rounded-full px-2 text-[10px] font-medium text-muted-foreground hover:bg-white/10 hover:text-foreground">
                  <Sparkles className="h-3 w-3 text-indigo-400" />
                  {style}
                  <ChevronDown className="h-3 w-3 opacity-50" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-40">
                <DropdownMenuItem onClick={() => setStyle('Formal')}>Formal (Padrão)</DropdownMenuItem>
                <DropdownMenuItem onClick={() => setStyle('Direto')}>Direto e Conciso</DropdownMenuItem>
                <DropdownMenuItem onClick={() => setStyle('Persuasivo')}>Persuasivo</DropdownMenuItem>
                <DropdownMenuItem onClick={() => setStyle('Meu Estilo')}>
                  <span className="text-indigo-400">Meu Estilo (IA)</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <div className="h-4 w-[1px] bg-white/10 mx-1" />

            <Button variant="ghost" size="icon" className="h-7 w-7 rounded-full text-muted-foreground hover:bg-white/10 hover:text-foreground">
              <Paperclip className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7 rounded-full text-muted-foreground hover:bg-white/10 hover:text-foreground">
              <AtSign className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7 rounded-full text-muted-foreground hover:bg-white/10 hover:text-foreground">
              <Hash className="h-3.5 w-3.5" />
            </Button>
          </div>

          <Button
            onClick={handleSend}
            disabled={!content.trim() || disabled}
            size="icon"
            className={cn(
              "h-8 w-8 rounded-lg transition-all",
              content.trim()
                ? "bg-indigo-600 text-white hover:bg-indigo-500 shadow-lg shadow-indigo-500/20"
                : "bg-white/5 text-muted-foreground hover:bg-white/10"
            )}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
      {/* Ambient Glow */}
      <div className="pointer-events-none absolute -inset-px -z-10 rounded-2xl bg-gradient-to-r from-indigo-500/20 via-purple-500/20 to-indigo-500/20 opacity-0 blur-xl transition-opacity duration-500 group-focus-within:opacity-100" />
    </div>
  );
}
