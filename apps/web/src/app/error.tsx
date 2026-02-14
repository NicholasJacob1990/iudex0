'use client';

import { useEffect } from 'react';

type ErrorPageProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  useEffect(() => {
    // Keep this quiet and predictable for dev/prod fallback rendering.
    console.error(error);
  }, [error]);

  return (
    <main
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 24,
        fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, sans-serif',
        background: '#f8fafc',
        color: '#0f172a',
      }}
    >
      <div style={{ maxWidth: 640, textAlign: 'center' }}>
        <h1 style={{ fontSize: 24, marginBottom: 12 }}>Ocorreu um erro</h1>
        <p style={{ color: '#475569', marginBottom: 16 }}>
          Falha ao renderizar esta página. Tente novamente.
        </p>
        <button
          onClick={reset}
          style={{
            border: '1px solid #0f172a',
            background: '#0f172a',
            color: '#fff',
            borderRadius: 10,
            padding: '10px 14px',
            cursor: 'pointer',
          }}
        >
          Tentar novamente
        </button>
      </div>
    </main>
  );
}

