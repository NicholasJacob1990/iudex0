import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#2563EB',
          light: '#3B82F6',
          dark: '#1D4ED8',
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
          info: '#2563EB',
        },
        severity: {
          critical: '#DC2626',
          warning: '#D97706',
          info: '#2563EB',
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
