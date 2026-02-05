import { useEffect, useState, useCallback } from 'react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastData {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
}

interface ToastProps {
  toast: ToastData;
  onDismiss: (id: string) => void;
}

const typeStyles: Record<ToastType, string> = {
  success: 'bg-green-50 border-green-200 text-green-800',
  error: 'bg-red-50 border-red-200 text-red-800',
  warning: 'bg-amber-50 border-amber-200 text-amber-800',
  info: 'bg-blue-50 border-blue-200 text-blue-800',
};

const typeIcons: Record<ToastType, string> = {
  success: 'M5 13l4 4L19 7',
  error: 'M6 18L18 6M6 6l12 12',
  warning: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
  info: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
};

function Toast({ toast, onDismiss }: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(() => {
      onDismiss(toast.id);
    }, toast.duration || 3000);

    return () => clearTimeout(timer);
  }, [toast.id, toast.duration, onDismiss]);

  return (
    <div
      className={`flex items-center gap-2 rounded-md border px-3 py-2 shadow-lg animate-in fade-in slide-in-from-top-2 ${typeStyles[toast.type]}`}
      role="alert"
    >
      <svg
        className="h-4 w-4 shrink-0"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path strokeLinecap="round" strokeLinejoin="round" d={typeIcons[toast.type]} />
      </svg>
      <span className="text-office-sm">{toast.message}</span>
      <button
        onClick={() => onDismiss(toast.id)}
        className="ml-auto shrink-0 rounded p-0.5 hover:bg-black/5"
        aria-label="Fechar"
      >
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

// Toast Container Component
interface ToastContainerProps {
  toasts: ToastData[];
  onDismiss: (id: string) => void;
}

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed right-3 top-3 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

// Hook for toast management
let toastId = 0;

export function useToast() {
  const [toasts, setToasts] = useState<ToastData[]>([]);

  const showToast = useCallback((message: string, type: ToastType, duration = 3000) => {
    const id = `toast-${++toastId}`;
    setToasts((prev) => [...prev, { id, message, type, duration }]);
    return id;
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const success = useCallback((message: string, duration?: number) => {
    return showToast(message, 'success', duration);
  }, [showToast]);

  const error = useCallback((message: string, duration?: number) => {
    return showToast(message, 'error', duration ?? 5000);
  }, [showToast]);

  const warning = useCallback((message: string, duration?: number) => {
    return showToast(message, 'warning', duration);
  }, [showToast]);

  const info = useCallback((message: string, duration?: number) => {
    return showToast(message, 'info', duration);
  }, [showToast]);

  return {
    toasts,
    showToast,
    dismissToast,
    success,
    error,
    warning,
    info,
  };
}

// Global toast state for use outside React components
type ToastListener = (toasts: ToastData[]) => void;
const listeners: Set<ToastListener> = new Set();
let globalToasts: ToastData[] = [];

function notifyListeners() {
  listeners.forEach((listener) => listener([...globalToasts]));
}

export const toast = {
  success: (message: string, duration = 3000) => {
    const id = `toast-${++toastId}`;
    globalToasts = [...globalToasts, { id, message, type: 'success', duration }];
    notifyListeners();
    setTimeout(() => toast.dismiss(id), duration);
    return id;
  },
  error: (message: string, duration = 5000) => {
    const id = `toast-${++toastId}`;
    globalToasts = [...globalToasts, { id, message, type: 'error', duration }];
    notifyListeners();
    setTimeout(() => toast.dismiss(id), duration);
    return id;
  },
  warning: (message: string, duration = 3000) => {
    const id = `toast-${++toastId}`;
    globalToasts = [...globalToasts, { id, message, type: 'warning', duration }];
    notifyListeners();
    setTimeout(() => toast.dismiss(id), duration);
    return id;
  },
  info: (message: string, duration = 3000) => {
    const id = `toast-${++toastId}`;
    globalToasts = [...globalToasts, { id, message, type: 'info', duration }];
    notifyListeners();
    setTimeout(() => toast.dismiss(id), duration);
    return id;
  },
  dismiss: (id: string) => {
    globalToasts = globalToasts.filter((t) => t.id !== id);
    notifyListeners();
  },
  subscribe: (listener: ToastListener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  getToasts: () => [...globalToasts],
};

// Hook to use global toast state
export function useGlobalToast() {
  const [toasts, setToasts] = useState<ToastData[]>(toast.getToasts());

  useEffect(() => {
    const unsubscribe = toast.subscribe(setToasts);
    return () => {
      unsubscribe();
    };
  }, []);

  return { toasts, dismissToast: toast.dismiss };
}
