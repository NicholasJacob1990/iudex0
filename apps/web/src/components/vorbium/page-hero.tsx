'use client';

import React from 'react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { PaintBackground } from '@/components/ui/paint-background';

type WorkletName = 'verbium-particles' | 'nebula-flow' | 'grid-pulse' | 'wave-field';

interface PageHeroProps {
    badge?: string;
    title: string;
    description: string;
    primaryCtaText: string;
    primaryCtaLink: string;
    secondaryCtaText?: string;
    secondaryCtaLink?: string;
    /** Paint worklet to use as background. Defaults to nebula-flow. */
    worklet?: WorkletName;
    /** Custom color for the worklet (hex). */
    workletColor?: string;
    /** Seed for the worklet randomness. */
    workletSeed?: number;
}

export function PageHero({
    badge,
    title,
    description,
    primaryCtaText,
    primaryCtaLink,
    secondaryCtaText,
    secondaryCtaLink,
    worklet = 'nebula-flow',
    workletColor,
    workletSeed,
}: PageHeroProps) {
    return (
        <section className="relative min-h-[60dvh] flex items-center justify-center overflow-hidden bg-slate-50 dark:bg-[#0a0a0c] text-slate-900 dark:text-white snap-start pt-20">
            {/* Paint Worklet Background */}
            <PaintBackground worklet={worklet} color={workletColor} seed={workletSeed} />

            {/* Background Effects */}
            <div className="absolute inset-0 z-[1] pointer-events-none">
                <div className="absolute inset-0 opacity-[0.04] bg-dotted-grid [background-size:24px_24px]" />
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-indigo-500/8 blur-[120px] rounded-full mix-blend-screen pointer-events-none" />
            </div>

            <div className="container relative z-10 px-6 mx-auto text-center">
                <div className="animate-reveal-up opacity-0 translate-y-8 [animation-timeline:view()] [animation-range:entry_0%_cover_30%]">
                    {badge && (
                        <div className="inline-flex items-center gap-2 px-4 py-2 mb-8 rounded-full bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 backdrop-blur-md shadow-sm dark:shadow-none">
                            <span className="text-sm font-medium text-indigo-600 dark:text-indigo-300 tracking-wide">{badge}</span>
                        </div>
                    )}

                    <h1 className="text-[2.5rem] md:text-[3.5rem] lg:text-[5rem] font-bold heading-section mb-8 max-w-4xl mx-auto text-slate-900 dark:text-white">
                        {title}
                    </h1>

                    <p className="max-w-2xl mx-auto text-xl text-slate-600 dark:text-gray-400 mb-12 leading-relaxed">
                        {description}
                    </p>

                    <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
                        <Link href={primaryCtaLink}>
                            <Button size="lg" className="h-12 px-8 rounded-full text-base bg-slate-900 dark:bg-white text-white dark:text-black hover:bg-slate-800 dark:hover:bg-gray-200 transition-all">
                                {primaryCtaText}
                            </Button>
                        </Link>
                        {secondaryCtaText && secondaryCtaLink && (
                            <Link href={secondaryCtaLink}>
                                <Button variant="ghost" size="lg" className="h-12 px-8 rounded-full text-base text-slate-600 dark:text-gray-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/5 border border-slate-200 dark:border-white/5 backdrop-blur-sm">
                                    {secondaryCtaText}
                                </Button>
                            </Link>
                        )}
                    </div>
                </div>
            </div>
        </section>
    );
}
