'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { TypingText } from '@/components/vorbium/typing-text';
import { useTheme } from 'next-themes';

export function HeroSection() {
    const containerRef = useRef<HTMLDivElement>(null);
    const [hasPaint, setHasPaint] = useState(false);
    const { theme, systemTheme } = useTheme();
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
        const supportsPaint = typeof CSS !== 'undefined' && 'paintWorklet' in CSS;

        if (supportsPaint) {
            Promise.all([
                // @ts-ignore
                CSS.paintWorklet.addModule('/worklets/verbium-particles.js'),
            ])
                .then(() => setHasPaint(true))
                .catch(() => setHasPaint(false));
        } else {
            setHasPaint(false);
        }
    }, []);

    const handlePointerMove = (e: React.PointerEvent<HTMLElement>) => {
        const container = containerRef.current;
        if (!container) return;

        const rect = container.getBoundingClientRect();
        // Normalize to 0-1 as per Recipe
        const x = (e.clientX - rect.left) / rect.width;
        const y = (e.clientY - rect.top) / rect.height;

        container.style.setProperty('--cursor-x', `${x}`);
        container.style.setProperty('--cursor-y', `${y}`);
    };

    const handlePointerLeave = () => {
        const container = containerRef.current;
        if (!container) return;

        // Reset to center
        container.style.setProperty('--cursor-x', '0.5');
        container.style.setProperty('--cursor-y', '0.5');
    };

    const currentTheme = theme === 'system' ? systemTheme : theme;
    const isDark = currentTheme === 'dark';
    const themeColor = isDark ? '#4f46e5' : '#4338ca';

    if (!mounted) return null;

    return (
        <section
            ref={containerRef}
            id="welcome"
            onPointerMove={handlePointerMove}
            onPointerLeave={handlePointerLeave}
            className="relative min-h-[100dvh] flex items-center justify-center overflow-hidden bg-slate-50 dark:bg-[#0a0a0c] text-slate-900 dark:text-white snap-start transition-colors duration-500"
            style={{
                // Defaults
                // @ts-ignore
                '--cursor-x': '0.5',
                '--cursor-y': '0.5',
                '--theme-color': themeColor,
                // The clock is now driven by CSS Keyframes defined in globals.css
                animation: 'vorbiumTime 60s linear infinite',

                backgroundImage: hasPaint ? 'paint(verbium-particles)' : 'none',
                background: hasPaint ? undefined : isDark
                    ? 'radial-gradient(circle at 50% 50%, #1e1b4b 0%, #0a0a0c 60%)'
                    : 'radial-gradient(circle at 50% 50%, #e0e7ff 0%, #f8fafc 60%)',
            }}
        >
            <div className="absolute inset-0 pointer-events-none">
                <div className="absolute inset-0 opacity-[0.03] dark:opacity-[0.04] bg-dotted-grid [background-size:24px_24px] animate-drift" />
                <div className="absolute inset-0 opacity-[0.04] dark:opacity-[0.06] noise-overlay" />
            </div>

            <div className="container relative z-10 px-6 mx-auto text-center pointer-events-none">
                <div className="animate-reveal-up opacity-0 translate-y-8 [animation-timeline:view()] [animation-range:entry_0%_cover_30%]">
                    <div className="inline-flex items-center gap-2 px-4 py-2 mb-8 rounded-full bg-indigo-500/5 dark:bg-indigo-500/10 border border-indigo-500/10 dark:border-indigo-500/20 backdrop-blur-md pointer-events-auto">
                        <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
                        </span>
                        <span className="text-sm font-medium text-indigo-600 dark:text-indigo-300 tracking-wide">Verbium AI Engine 3.0</span>
                    </div>

                    <h1 className="text-5xl md:text-7xl font-bold tracking-tight mb-8 bg-clip-text text-transparent bg-gradient-to-b from-slate-900 to-slate-600 dark:from-white dark:to-white/60">
                        <span className="block mb-2 text-slate-900 dark:text-white">
                            Um único sistema para
                        </span>
                        <div className="flex justify-center gap-2 text-indigo-600 dark:text-indigo-500 h-[1.2em]">
                            <TypingText text="interpretar, decidir e executar." duration="3.5s" delay="0.5s" />
                        </div>
                    </h1>

                    <p className="max-w-3xl mx-auto text-xl text-slate-600 dark:text-gray-400 mb-12 leading-relaxed pointer-events-auto">
                        A <span className="text-slate-900 dark:text-white font-medium">Verbium</span> integra assistentes tradicionais e orquestração multiagente para operar linguagem jurídica com rastreabilidade, auditabilidade e supervisão humana.
                    </p>

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

                    <div className="mt-16 grid gap-4 sm:grid-cols-3 max-w-4xl mx-auto text-left pointer-events-auto">
                        <div className="group rounded-2xl border border-slate-200 dark:border-white/10 bg-white/40 dark:bg-white/5 px-6 py-6 backdrop-blur transition-colors hover:border-indigo-500/30 hover:bg-indigo-500/5">
                            <p className="text-2xl font-semibold text-slate-800 dark:text-white mb-1 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">Assistentes</p>
                            <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500 dark:text-white/50">Raciocínio Jurídico</p>
                        </div>
                        <div className="group rounded-2xl border border-slate-200 dark:border-white/10 bg-white/40 dark:bg-white/5 px-6 py-6 backdrop-blur transition-colors hover:border-indigo-500/30 hover:bg-indigo-500/5">
                            <p className="text-2xl font-semibold text-slate-800 dark:text-white mb-1 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">Agentes</p>
                            <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500 dark:text-white/50">Execução Autônoma</p>
                        </div>
                        <div className="group rounded-2xl border border-slate-200 dark:border-white/10 bg-white/40 dark:bg-white/5 px-6 py-6 backdrop-blur transition-colors hover:border-indigo-500/30 hover:bg-indigo-500/5">
                            <p className="text-2xl font-semibold text-slate-800 dark:text-white mb-1 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">Governança</p>
                            <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500 dark:text-white/50">Controle Total</p>
                        </div>
                    </div>
                </div>

            </div>

            <div className="absolute bottom-0 left-0 w-full h-32 bg-gradient-to-t from-slate-50 dark:from-[#0a0a0c] to-transparent pointer-events-none transition-colors duration-500" />

            <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-[10px] uppercase tracking-[0.4em] text-slate-400 dark:text-white/40 animate-pulse">
                <span>Discovery</span>
                <div className="h-12 w-[1px] bg-gradient-to-b from-slate-400 dark:from-white/50 to-transparent" />
            </div>
        </section>
    );
}
