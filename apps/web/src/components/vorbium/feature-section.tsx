'use client';

import React from 'react';
import Image from 'next/image';
import { cn } from '@/lib/utils';
import { LucideIcon } from 'lucide-react';
import { AnimatedContainer, StaggerContainer } from '@/components/ui/animated-container';

interface FeatureItem {
    title: string;
    description: string;
    icon?: LucideIcon;
    /** Image/screenshot URL for split variant */
    image?: string;
}

interface FeatureSectionProps {
    title?: string;
    description?: string;
    features: FeatureItem[];
    className?: string;
    /** Visual variant: grid (default icon cards), split (image+text alternating), steps (numbered process) */
    variant?: 'grid' | 'split' | 'steps';
}

/* ---- Variant: Grid (original, enhanced) ---- */
function GridVariant({ features }: { features: FeatureItem[] }) {
    return (
        <StaggerContainer className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {features.map((feature, idx) => (
                <AnimatedContainer
                    key={idx}
                    delay={idx * 0.1}
                    className="group p-6 rounded-2xl bg-slate-100 dark:bg-white/5 border border-slate-200 dark:border-white/10 hover:bg-white dark:hover:bg-white/10 hover:shadow-lg dark:hover:shadow-none transition-all duration-500 ease-out glow-hover scroll-fade-up"
                >
                    {feature.icon && (
                        <div
                            className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-lg bg-indigo-100 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 group-hover:text-white group-hover:bg-indigo-600 dark:group-hover:bg-indigo-500 transition-colors"
                            style={{
                                animation: `wobble 4s ease-in-out ${idx * 0.3}s infinite`,
                            }}
                        >
                            <feature.icon className="h-6 w-6" />
                        </div>
                    )}
                    <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-2">{feature.title}</h3>
                    <p className="text-slate-600 dark:text-gray-400 text-sm leading-relaxed">
                        {feature.description}
                    </p>
                </AnimatedContainer>
            ))}
        </StaggerContainer>
    );
}

/* ---- Variant: Split (image + text, alternating sides) ---- */
function SplitVariant({ features }: { features: FeatureItem[] }) {
    return (
        <div className="space-y-24">
            {features.map((feature, idx) => {
                const isEven = idx % 2 === 0;
                return (
                    <div
                        key={idx}
                        className={cn(
                            'grid md:grid-cols-2 gap-12 items-center',
                            isEven ? '' : 'md:[direction:rtl]'
                        )}
                    >
                        {/* Media side */}
                        <div className={cn(
                            'scroll-scale-in',
                            isEven ? '' : 'md:[direction:ltr]'
                        )}>
                            {feature.image ? (
                                <div className="rounded-2xl overflow-hidden border border-slate-200 dark:border-white/10 shadow-xl">
                                    <Image
                                        src={feature.image}
                                        alt={feature.title}
                                        width={1200}
                                        height={900}
                                        sizes="(max-width: 768px) 100vw, 50vw"
                                        className="w-full h-auto"
                                        unoptimized
                                    />
                                </div>
                            ) : (
                                <div className="aspect-[4/3] rounded-2xl bg-gradient-to-br from-indigo-100 to-purple-50 dark:from-indigo-500/10 dark:to-purple-500/5 border border-slate-200 dark:border-white/10 flex items-center justify-center">
                                    {feature.icon && (
                                        <feature.icon className="h-16 w-16 text-indigo-300 dark:text-indigo-500/30" />
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Text side */}
                        <div className={cn(
                            'scroll-fade-up',
                            isEven ? '' : 'md:[direction:ltr]'
                        )}>
                            {feature.icon && (
                                <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-lg bg-indigo-100 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                                    <feature.icon className="h-6 w-6" />
                                </div>
                            )}
                            <h3 className="text-2xl md:text-3xl font-bold text-slate-900 dark:text-white mb-4 heading-section">
                                {feature.title}
                            </h3>
                            <p className="text-slate-600 dark:text-gray-400 text-lg leading-relaxed">
                                {feature.description}
                            </p>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

/* ---- Variant: Steps (numbered process with connecting line) ---- */
function StepsVariant({ features }: { features: FeatureItem[] }) {
    return (
        <div className="relative">
            {/* Connecting line */}
            <div className="hidden md:block absolute top-8 left-0 right-0 h-px bg-gradient-to-r from-transparent via-indigo-300 dark:via-indigo-500/30 to-transparent" />

            <div className={cn(
                'grid gap-8',
                features.length <= 3 ? 'md:grid-cols-3' : 'md:grid-cols-4',
            )}>
                {features.map((feature, idx) => (
                    <div key={idx} className="relative text-center scroll-fade-up">
                        {/* Step number */}
                        <div className="relative z-10 mx-auto mb-6 h-16 w-16 rounded-full bg-white dark:bg-[#0a0a0c] border-2 border-indigo-200 dark:border-indigo-500/30 flex items-center justify-center">
                            {feature.icon ? (
                                <feature.icon className="h-7 w-7 text-indigo-600 dark:text-indigo-400" />
                            ) : (
                                <span className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                                    {idx + 1}
                                </span>
                            )}
                        </div>

                        {/* Step label below circle */}
                        <div className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-500 dark:text-indigo-400/70 mb-2">
                            Etapa {idx + 1}
                        </div>

                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">
                            {feature.title}
                        </h3>
                        <p className="text-slate-600 dark:text-gray-400 text-sm leading-relaxed">
                            {feature.description}
                        </p>
                    </div>
                ))}
            </div>
        </div>
    );
}

export function FeatureSection({ title, description, features, className, variant = 'grid' }: FeatureSectionProps) {
    return (
        <section className={cn('py-24 relative snap-start', className)}>
            <div className="container mx-auto px-6">
                {(title || description) && (
                    <AnimatedContainer className="mb-16 max-w-3xl">
                        {title && (
                            <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-300/80 mb-6 uppercase tracking-[0.3em] text-xs font-semibold">
                                <span className="h-px w-10 bg-indigo-600/40 dark:bg-indigo-400/40" />
                                <span>Overview</span>
                            </div>
                        )}
                        {title && (
                            <h2 className="text-4xl lg:text-5xl font-bold heading-section mb-6 text-slate-900 dark:text-white">
                                {title}
                            </h2>
                        )}
                        {description && (
                            <p className="text-slate-600 dark:text-gray-400 text-lg leading-relaxed">{description}</p>
                        )}
                    </AnimatedContainer>
                )}

                {variant === 'grid' && <GridVariant features={features} />}
                {variant === 'split' && <SplitVariant features={features} />}
                {variant === 'steps' && <StepsVariant features={features} />}
            </div>
        </section>
    );
}
