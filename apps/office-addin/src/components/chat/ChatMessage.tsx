import DOMPurify from 'dompurify';
import type { Message } from '@/api/client';

interface ChatMessageProps {
  message: Message;
  isStreaming?: boolean;
}

export function ChatMessage({ message, isStreaming }: ChatMessageProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`mb-3 ${isUser ? 'text-right' : ''}`}>
      <div
        className={`inline-block max-w-[90%] rounded-lg px-3 py-2 text-left text-office-sm ${
          isUser
            ? 'bg-brand text-white'
            : 'bg-surface-tertiary text-text-primary'
        }`}
      >
        {/* Thinking indicator */}
        {message.thinking && !isUser && (
          <details className="mb-2">
            <summary className="cursor-pointer text-office-xs text-text-tertiary">
              Raciocinio
            </summary>
            <pre className="mt-1 whitespace-pre-wrap text-office-xs text-text-tertiary">
              {message.thinking}
            </pre>
          </details>
        )}

        {/* Content — sanitized HTML rendering */}
        <div
          className="chat-content whitespace-pre-wrap break-words"
          dangerouslySetInnerHTML={{
            __html: DOMPurify.sanitize(message.content, {
              ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'code', 'pre', 'br', 'p', 'ul', 'ol', 'li', 'a', 'span'],
              ALLOWED_ATTR: ['href', 'target', 'rel', 'class'],
              ALLOW_DATA_ATTR: false,
            }),
          }}
        />

        {/* Streaming cursor */}
        {isStreaming && (
          <span className="ml-0.5 inline-block h-4 w-1 animate-pulse bg-text-tertiary" />
        )}
      </div>
    </div>
  );
}
