'use client';

import React, { useRef } from 'react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { TypingText } from '@/components/vorbium/typing-text';
import { useTheme } from 'next-themes';
import { useVorbiumPaint } from '@/hooks/use-vorbium-paint';
import { MotionDiv, fadeUp, staggerContainer, smoothTransition } from '@/components/ui/motion';
import { useTilt } from '@/hooks/use-tilt';
import { ChevronDown } from 'lucide-react';

function TiltCard({ children, className }: { children: React.ReactNode; className?: string }) {
    const ref = useRef<HTMLDivElement>(null);
    useTilt(ref, 6);
    return (
        <div ref={ref} className={className}>
            {children}
        </div>
    );
}

export function HeroSection() {
    const containerRef = useRef<HTMLDivElement>(null);
    const { theme, systemTheme } = useTheme();

    useVorbiumPaint(containerRef);

    const currentTheme = theme === 'system' ? systemTheme : theme;
    const isDark = currentTheme === 'dark';
    const themeColor = isDark ? '#6366f1' : '#4f46e5';

    return (
        <section
            ref={containerRef}
            id="welcome"
            className="relative min-h-[100dvh] flex items-center justify-center overflow-hidden bg-slate-50 dark:bg-[#0a0a0c] text-slate-900 dark:text-white snap-start transition-colors duration-500"
            style={{
                // @ts-ignore
                '--cursor-x': '0.5',
                '--cursor-y': '0.5',
                '--theme-color': themeColor,
                '--seed': '42',
                '--ring-radius': '140',
                '--ring-thickness': '380',
                '--particle-count': '120',
                '--particle-rows': '30',
                '--particle-size': '2.8',
                '--particle-min-alpha': '0.08',
                '--particle-max-alpha': '0.95',

                // Ring animations: ripple (wave cycle) + ring breathing + vorbiumTime (clock)
                animation: 'ripple 6s linear infinite, ringBreathe 6s ease-in-out infinite alternate, vorbiumTime 60s linear infinite',

                // Smooth cursor tracking for organic ring drift + responsive repulsion
                transition: '--cursor-x 0.3s cubic-bezier(0.2, 0.8, 0.2, 1), --cursor-y 0.3s cubic-bezier(0.2, 0.8, 0.2, 1)',

                backgroundImage: isDark
                    ? 'paint(verbium-particles), radial-gradient(circle at 50% 50%, #1e1b4b 0%, #0a0a0c 60%)'
                    : 'paint(verbium-particles), radial-gradient(circle at 50% 50%, #e0e7ff 0%, #f8fafc 60%)',
            }}
        >

            <div className="absolute inset-0 pointer-events-none">
                <div className="absolute inset-0 opacity-[0.03] dark:opacity-[0.04] bg-dotted-grid [background-size:24px_24px] animate-drift" />
                <div className="absolute inset-0 opacity-[0.04] dark:opacity-[0.06] noise-overlay" />
            </div>

            <div className="container relative z-10 px-6 mx-auto text-center pointer-events-none">
                <MotionDiv
                    variants={staggerContainer}
                    initial="hidden"
                    animate="visible"
                >
                    {/* Badge */}
                    <MotionDiv variants={fadeUp} transition={smoothTransition}>
                        <div className="inline-flex items-center gap-2 px-4 py-2 mb-8 rounded-full bg-indigo-500/5 dark:bg-indigo-500/10 border border-indigo-500/10 dark:border-indigo-500/20 backdrop-blur-md pointer-events-auto">
                            <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
                            </span>
                            <span className="text-sm font-medium text-indigo-600 dark:text-indigo-300 tracking-wide">Vorbium AI Engine 3.0</span>
                        </div>
                    </MotionDiv>

                    {/* Heading */}
                    <MotionDiv variants={fadeUp} transition={smoothTransition}>
                        <h1 className="text-5xl md:text-7xl font-bold tracking-tight mb-8 bg-clip-text text-transparent bg-gradient-to-b from-slate-900 to-slate-600 dark:from-white dark:to-white/60">
                            <span className="block mb-2 text-slate-900 dark:text-white">
                                Um único sistema para
                            </span>
                            <div className="flex justify-center gap-2 text-indigo-600 dark:text-indigo-500 h-[1.2em]">
                                <TypingText text="interpretar, decidir e executar." duration="3.5s" delay="0.5s" />
                            </div>
                        </h1>
                    </MotionDiv>

                    {/* Description */}
                    <MotionDiv variants={fadeUp} transition={smoothTransition}>
                        <p className="max-w-3xl mx-auto text-xl text-slate-600 dark:text-gray-400 mb-12 leading-relaxed pointer-events-auto">
                            A <span className="text-slate-900 dark:text-white font-medium">Vorbium</span> integra assistentes tradicionais e orquestração multiagente para operar linguagem jurídica com rastreabilidade, auditabilidade e supervisão humana.
                        </p>
                    </MotionDiv>

                    {/* CTA Buttons */}
                    <MotionDiv variants={fadeUp} transition={smoothTransition}>
                        <div className="flex flex-col sm:flex-row items-center justify-center gap-6 pointer-events-auto">
                            <Link href="/demo">
                                <Button size="lg" className="h-14 px-8 rounded-full text-lg bg-indigo-600 hover:bg-indigo-700 dark:hover:bg-indigo-500 text-white shadow-[0_0_20px_-5px_rgba(79,70,229,0.3)] dark:shadow-[0_0_40px_-10px_rgba(79,70,229,0.5)] transition-all hover:scale-105 border-0">
                                    Solicitar demonstração
                                </Button>
                            </Link>
                            <Link href="/login">
                                <Button variant="outline" size="lg" className="h-14 px-8 rounded-full text-lg border-slate-200 dark:border-white/10 bg-white/50 dark:bg-white/5 hover:bg-white/80 dark:hover:bg-white/10 text-slate-700 dark:text-white backdrop-blur-sm transition-all hover:scale-105">
                                    Acessar Plataforma
                                </Button>
                            </Link>
                        </div>
                    </MotionDiv>

                    {/* Feature Cards with Tilt */}
                    <MotionDiv variants={fadeUp} transition={smoothTransition}>
                        <div className="mt-16 grid gap-4 sm:grid-cols-3 max-w-4xl mx-auto text-left pointer-events-auto">
                            <TiltCard className="group rounded-2xl border border-slate-200 dark:border-white/10 bg-white/40 dark:bg-white/5 px-6 py-6 backdrop-blur transition-colors hover:border-indigo-500/30 hover:bg-indigo-500/5">
                                <p className="text-2xl font-semibold text-slate-800 dark:text-white mb-1 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">Assistentes</p>
                                <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500 dark:text-white/50">Raciocínio Jurídico</p>
                            </TiltCard>
                            <TiltCard className="group rounded-2xl border border-slate-200 dark:border-white/10 bg-white/40 dark:bg-white/5 px-6 py-6 backdrop-blur transition-colors hover:border-indigo-500/30 hover:bg-indigo-500/5">
                                <p className="text-2xl font-semibold text-slate-800 dark:text-white mb-1 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">Agentes</p>
                                <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500 dark:text-white/50">Execução Autônoma</p>
                            </TiltCard>
                            <TiltCard className="group rounded-2xl border border-slate-200 dark:border-white/10 bg-white/40 dark:bg-white/5 px-6 py-6 backdrop-blur transition-colors hover:border-indigo-500/30 hover:bg-indigo-500/5">
                                <p className="text-2xl font-semibold text-slate-800 dark:text-white mb-1 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">Governança</p>
                                <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500 dark:text-white/50">Controle Total</p>
                            </TiltCard>
                        </div>
                    </MotionDiv>
                </MotionDiv>

            </div>

            <div className="absolute bottom-0 left-0 w-full h-32 bg-gradient-to-t from-slate-50 dark:from-[#0a0a0c] to-transparent pointer-events-none transition-colors duration-500" />

            {/* Scroll indicator with animated chevron */}
            <MotionDiv
                className="absolute bottom-6 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-[10px] uppercase tracking-[0.4em] text-slate-400 dark:text-white/40"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 2, duration: 0.8 }}
            >
                <span>Discovery</span>
                <MotionDiv
                    animate={{ y: [0, 6, 0] }}
                    transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
                >
                    <ChevronDown className="h-5 w-5" />
                </MotionDiv>
                <div className="h-8 w-[1px] bg-gradient-to-b from-slate-400 dark:from-white/50 to-transparent" />
            </MotionDiv>
        </section>
    );
}
