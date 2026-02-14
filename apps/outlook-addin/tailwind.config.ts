import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#4F46E5',
          light: '#6366F1',
          dark: '#4338CA',
        },
        surface: {
          DEFAULT: '#FFFFFF',
          secondary: '#F8FAFC',
          tertiary: '#F1F5F9',
        },
        text: {
          primary: '#0F172A',
          secondary: '#475569',
          tertiary: '#94A3B8',
        },
        status: {
          success: '#16A34A',
          warning: '#D97706',
          error: '#DC2626',
          info: '#4F46E5',
        },
        urgency: {
          alta: '#DC2626',
          media: '#D97706',
          baixa: '#16A34A',
        },
      },
      fontSize: {
        'office-xs': ['11px', '16px'],
        'office-sm': ['12px', '18px'],
        'office-base': ['13px', '20px'],
        'office-lg': ['14px', '22px'],
      },
      spacing: {
        'office-xs': '4px',
        'office-sm': '8px',
        'office-md': '12px',
        'office-lg': '16px',
      },
    },
  },
  plugins: [],
};

export default config;
