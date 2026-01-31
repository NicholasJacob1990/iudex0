'use client';

import React from 'react';

interface TypingTextProps {
    text: string;
    className?: string; // Custom class for styling
    duration?: string;  // e.g. "3s"
    delay?: string;     // e.g. "0s"
}

export function TypingText({ text, className = "", duration = "3.5s", delay = "0.5s" }: TypingTextProps) {
    const charCount = Math.max(12, text.length);

    return (
        <div
            className={`relative inline-block overflow-hidden whitespace-nowrap border-r-4 border-indigo-500 pr-1 ${className}`}
            style={{
                // @ts-ignore -- CSS custom properties for inline style
                '--chars': charCount,
                animation: `typing ${duration} steps(${charCount}, end) forwards, blink-caret .75s step-end infinite`,
                animationDelay: delay,
                width: '0', // Start hidden
            }}
        >
            {text}
            <style jsx>{`
        @keyframes typing {
          from { width: 0 }
          to { width: calc(var(--chars) * 1ch) }
        }
        @keyframes blink-caret {
          from, to { border-color: transparent }
          50% { border-color: #6366f1 } /* Indigo-500 */
        }
      `}</style>
        </div>
    );
}
