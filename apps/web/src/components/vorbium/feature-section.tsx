'use client';

import React from 'react';
import { cn } from '@/lib/utils';
import { LucideIcon } from 'lucide-react';

interface FeatureItem {
    title: string;
    description: string;
    icon?: LucideIcon;
}

interface FeatureSectionProps {
    title?: string;
    description?: string;
    features: FeatureItem[];
    className?: string;
}

export function FeatureSection({ title, description, features, className }: FeatureSectionProps) {
    return (
        <section className={cn("py-24 relative snap-start", className)}>
            <div className="container mx-auto px-6">
                {(title || description) && (
                    <div className="mb-16 max-w-3xl">
                        {title && (
                            <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-300/80 mb-6 uppercase tracking-[0.3em] text-xs font-semibold">
                                <span className="h-px w-10 bg-indigo-600/40 dark:bg-indigo-400/40" />
                                <span>Overview</span>
                            </div>
                        )}
                        {title && <h2 className="text-4xl lg:text-5xl font-bold mb-6 leading-tight text-slate-900 dark:text-white">{title}</h2>}
                        {description && <p className="text-slate-600 dark:text-gray-400 text-lg leading-relaxed">{description}</p>}
                    </div>
                )}

                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {features.map((feature, idx) => (
                        <div key={idx} className="group p-6 rounded-2xl bg-slate-100 dark:bg-white/5 border border-slate-200 dark:border-white/10 hover:bg-white dark:hover:bg-white/10 hover:shadow-lg dark:hover:shadow-none transition-all">
                            {feature.icon && (
                                <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-lg bg-indigo-100 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 group-hover:text-white group-hover:bg-indigo-600 dark:group-hover:bg-indigo-500 transition-colors">
                                    <feature.icon className="h-6 w-6" />
                                </div>
                            )}
                            <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-2">{feature.title}</h3>
                            <p className="text-slate-600 dark:text-gray-400 text-sm leading-relaxed">
                                {feature.description}
                            </p>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}
