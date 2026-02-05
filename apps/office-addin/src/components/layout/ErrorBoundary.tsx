import { Component, type ReactNode, type ErrorInfo } from 'react';

interface Props {
  children: ReactNode;
  fallbackLabel?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-3 p-office-md text-center">
          <p className="text-office-base font-semibold text-status-error">
            Erro ao carregar {this.props.fallbackLabel || 'conteudo'}
          </p>
          <p className="max-w-xs text-office-xs text-text-tertiary">
            {this.state.error?.message || 'Erro desconhecido'}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="office-btn-secondary text-office-xs"
          >
            Tentar novamente
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
