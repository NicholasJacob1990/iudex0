import { mixHex } from '@/components/layout/top-nav';
import { type TintMode } from '@/stores/ui-store';

type SurfaceStyle = {
  backgroundColor?: string;
  borderColor?: string;
};

export type ChatTintStyles = {
  messageAreaStyle?: SurfaceStyle;
  assistantBubbleStyle?: SurfaceStyle;
  inputAreaStyle?: SurfaceStyle;
  canvasStyle?: SurfaceStyle;
};

type ChatTintStyleParams = {
  tintMode: TintMode;
  isDark: boolean;
  chatBg: string;
};

export function getChatTintStyles({ tintMode, isDark, chatBg }: ChatTintStyleParams): ChatTintStyles {
  if (tintMode === 'uniform') {
    return {
      messageAreaStyle: { backgroundColor: chatBg },
      assistantBubbleStyle: { backgroundColor: chatBg, borderColor: 'transparent' },
      inputAreaStyle: { backgroundColor: chatBg, borderColor: 'transparent' },
      canvasStyle: { backgroundColor: chatBg },
    };
  }

  if (tintMode === 'inset') {
    return {
      messageAreaStyle: {
        backgroundColor: mixHex(chatBg, isDark ? '#f8fafc' : '#ffffff', isDark ? 0.90 : 0.95),
      },
      assistantBubbleStyle: {
        backgroundColor: mixHex(chatBg, isDark ? '#f8fafc' : '#ffffff', isDark ? 0.90 : 0.94),
        borderColor: mixHex(chatBg, isDark ? '#334155' : '#cbd5e1', 0.25),
      },
      inputAreaStyle: {
        backgroundColor: chatBg,
        borderColor: mixHex(chatBg, isDark ? '#334155' : '#cbd5e1', 0.35),
      },
      canvasStyle: { backgroundColor: chatBg },
    };
  }

  if (tintMode === 'blended') {
    if (isDark) {
      return {
        messageAreaStyle: { backgroundColor: mixHex(chatBg, '#0f172a', 0.34) },
        assistantBubbleStyle: {
          backgroundColor: mixHex(chatBg, '#1e293b', 0.68),
          borderColor: mixHex(chatBg, '#64748b', 0.55),
        },
        inputAreaStyle: {
          backgroundColor: mixHex(chatBg, '#020617', 0.82),
          borderColor: mixHex(chatBg, '#334155', 0.55),
        },
        canvasStyle: { backgroundColor: mixHex(chatBg, '#020617', 0.76) },
      };
    }

    return {
      messageAreaStyle: { backgroundColor: mixHex(chatBg, '#ffffff', 0.50) },
      assistantBubbleStyle: {
        backgroundColor: mixHex(chatBg, '#ffffff', 0.93),
        borderColor: mixHex(chatBg, '#94a3b8', 0.42),
      },
      inputAreaStyle: {
        backgroundColor: mixHex(chatBg, '#ffffff', 0.45),
        borderColor: mixHex(chatBg, '#94a3b8', 0.35),
      },
      canvasStyle: { backgroundColor: mixHex(chatBg, '#ffffff', 0.32) },
    };
  }

  // layered
  return {};
}
