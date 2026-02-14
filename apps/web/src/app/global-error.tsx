'use client';

import { useEffect } from 'react';

type GlobalErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function GlobalError({ error, reset }: GlobalErrorProps) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="pt-BR">
      <body
        style={{
          margin: 0,
          minHeight: '100vh',
          display: 'grid',
          placeItems: 'center',
          padding: 24,
          fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, sans-serif',
          background: '#0f172a',
          color: '#e2e8f0',
        }}
      >
        <div style={{ maxWidth: 680, textAlign: 'center' }}>
          <h1 style={{ fontSize: 24, marginBottom: 12 }}>
            Erro inesperado da aplicação
          </h1>
          <p style={{ color: '#cbd5e1', marginBottom: 16 }}>
            Ocorreu uma falha global de renderização.
          </p>
          <button
            onClick={reset}
            style={{
              border: '1px solid #e2e8f0',
              background: 'transparent',
              color: '#e2e8f0',
              borderRadius: 10,
              padding: '10px 14px',
              cursor: 'pointer',
            }}
          >
            Recarregar aplicação
          </button>
        </div>
      </body>
    </html>
  );
}

