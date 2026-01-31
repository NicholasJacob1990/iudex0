'use client';

import React, { useMemo } from 'react';

type SplitTextProps = {
  text: string;
  className?: string;
  perCharDelayMs?: number;
};

export function SplitText({ text, className = '', perCharDelayMs = 18 }: SplitTextProps) {
  const chars = useMemo(() => Array.from(text), [text]);

  return (
    <span className={className} aria-label={text}>
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">
        {chars.map((ch, i) => (
          <span
            key={`${ch}-${i}`}
            className="inline-block opacity-0 animate-char-in will-change-transform"
            style={{ animationDelay: `${i * perCharDelayMs}ms` }}
          >
            {ch === ' ' ? '\u00A0' : ch}
          </span>
        ))}
      </span>
    </span>
  );
}

