'use client';

import React from 'react';

interface LogoItem {
    name: string;
    /** SVG element or image */
    logo: React.ReactNode;
}

interface LogoCarouselProps {
    logos: LogoItem[];
    className?: string;
}

/**
 * Infinite-scrolling logo carousel using CSS animation.
 * Duplicates the list to create a seamless loop.
 */
export function LogoCarousel({ logos, className }: LogoCarouselProps) {
    if (logos.length === 0) return null;

    return (
        <div className={`w-full overflow-hidden ${className ?? ''}`}>
            <div className="flex animate-logo-scroll" style={{ width: 'max-content' }}>
                {/* First set */}
                <div className="flex items-center gap-16 px-8">
                    {logos.map((item, i) => (
                        <div
                            key={`a-${i}`}
                            className="flex items-center gap-3 opacity-40 hover:opacity-70 transition-opacity duration-300 shrink-0"
                            title={item.name}
                        >
                            <span className="h-8 w-auto [&>svg]:h-8 [&>svg]:w-auto text-slate-400 dark:text-white/40">
                                {item.logo}
                            </span>
                            <span className="text-sm font-medium text-slate-400 dark:text-white/40 whitespace-nowrap hidden sm:block">
                                {item.name}
                            </span>
                        </div>
                    ))}
                </div>
                {/* Duplicate for seamless loop */}
                <div className="flex items-center gap-16 px-8" aria-hidden>
                    {logos.map((item, i) => (
                        <div
                            key={`b-${i}`}
                            className="flex items-center gap-3 opacity-40 hover:opacity-70 transition-opacity duration-300 shrink-0"
                        >
                            <span className="h-8 w-auto [&>svg]:h-8 [&>svg]:w-auto text-slate-400 dark:text-white/40">
                                {item.logo}
                            </span>
                            <span className="text-sm font-medium text-slate-400 dark:text-white/40 whitespace-nowrap hidden sm:block">
                                {item.name}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
