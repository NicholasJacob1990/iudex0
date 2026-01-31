import type { Config } from 'tailwindcss';

const config: Config = {
	darkMode: ['class'],
	content: [
		'./src/pages/**/*.{js,ts,jsx,tsx,mdx}',
		'./src/components/**/*.{js,ts,jsx,tsx,mdx}',
		'./src/app/**/*.{js,ts,jsx,tsx,mdx}',
	],
	theme: {
		container: {
			center: true,
			padding: '2rem',
			screens: {
				'2xl': '1400px'
			}
		},
		extend: {
			fontFamily: {
				sans: [
					'var(--font-sans)',
					'Inter',
					'sans-serif'
				],
				display: [
					'var(--font-display)',
					'Sora',
					'sans-serif'
				]
			},
			colors: {
				border: 'hsl(var(--border))',
				input: 'hsl(var(--input))',
				ring: 'hsl(var(--ring))',
				background: 'hsl(var(--background))',
				foreground: 'hsl(var(--foreground))',
				primary: {
					DEFAULT: 'hsl(var(--primary))',
					foreground: 'hsl(var(--primary-foreground))'
				},
				secondary: {
					DEFAULT: 'hsl(var(--secondary))',
					foreground: 'hsl(var(--secondary-foreground))'
				},
				destructive: {
					DEFAULT: 'hsl(var(--destructive))',
					foreground: 'hsl(var(--destructive-foreground))'
				},
				muted: {
					DEFAULT: 'hsl(var(--muted))',
					foreground: 'hsl(var(--muted-foreground))'
				},
				accent: {
					DEFAULT: 'hsl(var(--accent))',
					foreground: 'hsl(var(--accent-foreground))'
				},
				popover: {
					DEFAULT: 'hsl(var(--popover))',
					foreground: 'hsl(var(--popover-foreground))'
				},
				card: {
					DEFAULT: 'hsl(var(--card))',
					foreground: 'hsl(var(--card-foreground))'
				},
				// Vorbium Trust Blue Palette
				vorbium: {
					deep: '#0F172A', // Slate 900
					dark: '#1E293B', // Slate 800
					neutral: '#334155', // Slate 700
					light: '#94A3B8', // Slate 400
					pale: '#E2E8F0', // Slate 200
					accent: '#22D3EE', // Cyan 400
					'accent-hover': '#06B6D4', // Cyan 500
					'primary-blue': '#2563EB', // Blue 600
				},
				sand: 'hsl(var(--sand))',
				clay: 'hsl(var(--clay))',
				blush: 'hsl(var(--blush))',
				lavender: 'hsl(var(--lavender))',
				emerald: 'hsl(var(--emerald))',
				panel: 'hsl(var(--panel))',
				outline: 'hsl(var(--outline))',
				chart: {
					'1': 'hsl(var(--chart-1))',
					'2': 'hsl(var(--chart-2))',
					'3': 'hsl(var(--chart-3))',
					'4': 'hsl(var(--chart-4))',
					'5': 'hsl(var(--chart-5))'
				}
			},
			borderRadius: {
				lg: 'var(--radius)',
				md: 'calc(var(--radius) - 2px)',
				sm: 'calc(var(--radius) - 4px)'
			},
			boxShadow: {
				soft: '0 24px 60px rgba(15, 23, 42, 0.08)',
				'soft-lg': '0 35px 120px rgba(15, 23, 42, 0.18)',
				inner: 'inset 0 1px 0 rgba(255, 255, 255, 0.6)'
			},
			backgroundImage: {
				'dotted-grid': 'radial-gradient(circle at 1px 1px, rgba(15,23,42,0.06) 1px, transparent 0)'
			},
			spacing: {
				'18': '4.5rem'
			},
			keyframes: {
				'accordion-down': {
					from: {
						height: '0'
					},
					to: {
						height: 'var(--radix-accordion-content-height)'
					}
				},
				'accordion-up': {
					from: {
						height: 'var(--radix-accordion-content-height)'
					},
					to: {
						height: '0'
					}
				},
				shimmer: {
					'0%': {
						backgroundPosition: '-700px 0'
					},
					'100%': {
						backgroundPosition: '700px 0'
					}
				},
				'reveal-up': {
					'0%': { opacity: '0', transform: 'translateY(2rem)' },
					'100%': { opacity: '1', transform: 'translateY(0)' }
				},
				float: {
					'0%, 100%': { transform: 'translateY(0)' },
					'50%': { transform: 'translateY(-12px)' }
				},
				drift: {
					'0%, 100%': { transform: 'translate(-1.5%, -1.5%)' },
					'50%': { transform: 'translate(1.5%, 1.5%)' }
				},
				'stream-in': {
					'0%': { opacity: '0', transform: 'translateX(2.5rem)' },
					'100%': { opacity: '1', transform: 'translateX(0)' }
				},
				'char-in': {
					'0%': { opacity: '0', transform: 'translateY(0.7em)', filter: 'blur(10px)' },
					'100%': { opacity: '1', transform: 'translateY(0)', filter: 'blur(0px)' }
				}
			},
			animation: {
				'accordion-down': 'accordion-down 0.2s ease-out',
				'accordion-up': 'accordion-up 0.2s ease-out',
				shimmer: 'shimmer 2s infinite linear',
				'reveal-up': 'reveal-up 1s ease-in-out forwards',
				float: 'float 6s ease-in-out infinite',
				drift: 'drift 12s ease-in-out infinite',
				'stream-in': 'stream-in 900ms cubic-bezier(.19,1,.22,1) forwards',
				'char-in': 'char-in 700ms cubic-bezier(.19,1,.22,1) forwards'
			}
		}
	},
	plugins: [require('tailwindcss-animate')],
};

export default config;
