'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { AnimatedCounter } from '@/components/ui/animated-counter';

interface Testimonial {
    quote: string;
    name: string;
    role: string;
    company: string;
    initials: string;
    gradientFrom: string;
    gradientTo: string;
}

interface Stat {
    value: number;
    suffix: string;
    label: string;
}

interface TestimonialsSectionProps {
    testimonials?: Testimonial[];
    stats?: Stat[];
    className?: string;
}

const DEFAULT_TESTIMONIALS: Testimonial[] = [
    {
        quote: 'A Vorbium transformou nossa pesquisa jurisprudencial. O que levava dias, agora leva minutos com rastreabilidade completa.',
        name: 'Maria Silva',
        role: 'Socia',
        company: 'Escritorio XYZ Advogados',
        initials: 'MS',
        gradientFrom: '#6366f1',
        gradientTo: '#8b5cf6',
    },
    {
        quote: 'A automacao de minutas com supervisao humana nos deu confianca para escalar a operacao juridica sem perder qualidade.',
        name: 'Carlos Mendes',
        role: 'Diretor Juridico',
        company: 'Empresa ABC',
        initials: 'CM',
        gradientFrom: '#06b6d4',
        gradientTo: '#3b82f6',
    },
    {
        quote: 'Finalmente uma IA que cita fontes e reconhece os limites do que pode afirmar. Essencial para governanca corporativa.',
        name: 'Ana Ferreira',
        role: 'Compliance Officer',
        company: 'Grupo Delta',
        initials: 'AF',
        gradientFrom: '#10b981',
        gradientTo: '#06b6d4',
    },
];

const DEFAULT_STATS: Stat[] = [
    { value: 500, suffix: '+', label: 'minutas geradas/mes' },
    { value: 98, suffix: '%', label: 'precisao em citacoes' },
    { value: 3, suffix: 'x', label: 'mais rapido' },
];

const slideVariants = {
    enter: (dir: number) => ({ x: dir > 0 ? 200 : -200, opacity: 0 }),
    center: { x: 0, opacity: 1 },
    exit: (dir: number) => ({ x: dir > 0 ? -200 : 200, opacity: 0 }),
};

export function TestimonialsSection({
    testimonials = DEFAULT_TESTIMONIALS,
    stats = DEFAULT_STATS,
    className,
}: TestimonialsSectionProps) {
    const [current, setCurrent] = useState(0);
    const [direction, setDirection] = useState(1);

    const next = useCallback(() => {
        setDirection(1);
        setCurrent((prev) => (prev + 1) % testimonials.length);
    }, [testimonials.length]);

    const prev = useCallback(() => {
        setDirection(-1);
        setCurrent((prev) => (prev - 1 + testimonials.length) % testimonials.length);
    }, [testimonials.length]);

    // Auto-play
    useEffect(() => {
        const timer = setInterval(next, 5000);
        return () => clearInterval(timer);
    }, [next]);

    const t = testimonials[current];

    return (
        <section className={`py-24 relative snap-start ${className ?? ''}`}>
            <div className="container mx-auto px-6 max-w-4xl">
                {/* Heading */}
                <h2 className="text-3xl md:text-5xl font-bold heading-section text-center mb-16 text-slate-900 dark:text-white">
                    Confiado por quem decide com precisao
                </h2>

                {/* Quote Carousel */}
                <div className="relative min-h-[260px] flex items-center justify-center">
                    <AnimatePresence mode="wait" custom={direction}>
                        <motion.div
                            key={current}
                            custom={direction}
                            variants={slideVariants}
                            initial="enter"
                            animate="center"
                            exit="exit"
                            transition={{ duration: 0.4, ease: [0.2, 0.8, 0.2, 1] }}
                            className="absolute inset-0 flex flex-col items-center text-center px-4"
                        >
                            {/* Quote */}
                            <blockquote className="text-xl md:text-2xl text-slate-700 dark:text-gray-300 leading-relaxed mb-8 max-w-3xl italic">
                                &ldquo;{t.quote}&rdquo;
                            </blockquote>

                            {/* Author */}
                            <div className="flex items-center gap-3">
                                <div
                                    className="h-10 w-10 rounded-full flex items-center justify-center text-white text-sm font-bold"
                                    style={{ background: `linear-gradient(135deg, ${t.gradientFrom}, ${t.gradientTo})` }}
                                >
                                    {t.initials}
                                </div>
                                <div className="text-left">
                                    <p className="text-sm font-semibold text-slate-800 dark:text-white">{t.name}</p>
                                    <p className="text-xs text-slate-500 dark:text-gray-400">{t.role}, {t.company}</p>
                                </div>
                            </div>
                        </motion.div>
                    </AnimatePresence>
                </div>

                {/* Navigation dots + arrows */}
                <div className="flex items-center justify-center gap-4 mt-8">
                    <button type="button" onClick={prev} className="p-1 text-slate-400 hover:text-slate-700 dark:hover:text-white transition-colors">
                        <ChevronLeft className="h-5 w-5" />
                    </button>
                    <div className="flex gap-2">
                        {testimonials.map((_, i) => (
                            <button
                                type="button"
                                key={i}
                                onClick={() => { setDirection(i > current ? 1 : -1); setCurrent(i); }}
                                className={`h-2 rounded-full transition-all duration-300 ${i === current ? 'w-6 bg-indigo-500' : 'w-2 bg-slate-300 dark:bg-white/20'}`}
                            />
                        ))}
                    </div>
                    <button type="button" onClick={next} className="p-1 text-slate-400 hover:text-slate-700 dark:hover:text-white transition-colors">
                        <ChevronRight className="h-5 w-5" />
                    </button>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-3 gap-8 mt-16 max-w-2xl mx-auto">
                    {stats.map((stat, i) => (
                        <div key={i} className="text-center">
                            <p className="text-3xl md:text-4xl font-bold text-indigo-600 dark:text-indigo-400">
                                <AnimatedCounter to={stat.value} duration={1.5} />
                                {stat.suffix}
                            </p>
                            <p className="text-sm text-slate-500 dark:text-gray-400 mt-1">{stat.label}</p>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}
