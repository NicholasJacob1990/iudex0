'use client';

import React, { useState } from 'react';
import Image from 'next/image';
import { Play, Image as ImageIcon } from 'lucide-react';
import { AnimatedContainer } from '@/components/ui/animated-container';

interface MediaItem {
    type: 'video' | 'image';
    /** Source URL. Leave empty for placeholder. */
    src?: string;
    /** Poster image for videos. */
    poster?: string;
    /** Label shown below the media. */
    label?: string;
}

interface MediaShowcaseProps {
    title?: string;
    subtitle?: string;
    /** Single item = centered hero media. Multiple = gallery grid. */
    media: MediaItem[];
    className?: string;
    /** Show browser chrome around media. Default: true */
    browserChrome?: boolean;
}

function BrowserChrome({ title, children }: { title?: string; children: React.ReactNode }) {
    return (
        <div className="rounded-2xl overflow-hidden border border-slate-200 dark:border-white/10 shadow-2xl bg-slate-900">
            <div className="h-10 bg-slate-800/80 flex items-center px-4 gap-2">
                <div className="h-3 w-3 rounded-full bg-red-400/60" />
                <div className="h-3 w-3 rounded-full bg-yellow-400/60" />
                <div className="h-3 w-3 rounded-full bg-green-400/60" />
                {title && <span className="ml-4 text-xs text-slate-400">{title}</span>}
            </div>
            {children}
        </div>
    );
}

function MediaPlaceholder({ type, label }: { type: 'video' | 'image'; label?: string }) {
    return (
        <div className="aspect-video bg-gradient-to-br from-indigo-600/20 via-purple-600/10 to-slate-900 flex items-center justify-center">
            <div className="flex flex-col items-center gap-4">
                {type === 'video' ? (
                    <div className="h-20 w-20 rounded-full bg-white/10 backdrop-blur-xl flex items-center justify-center border border-white/20 hover:scale-110 transition-transform duration-300 cursor-pointer">
                        <Play className="h-8 w-8 text-white ml-1" />
                    </div>
                ) : (
                    <div className="h-20 w-20 rounded-full bg-white/10 backdrop-blur-xl flex items-center justify-center border border-white/20">
                        <ImageIcon className="h-8 w-8 text-white" />
                    </div>
                )}
                {label && <span className="text-white/70 text-sm">{label}</span>}
            </div>
        </div>
    );
}

function VideoPlayer({ src, poster, label }: { src: string; poster?: string; label?: string }) {
  const [playing, setPlaying] = useState(false);

  if (!playing) {
    return (
      <div
        className="aspect-video relative cursor-pointer group"
        onClick={() => setPlaying(true)}
      >
        {poster ? (
          <Image
            src={poster}
            alt={label ?? 'Video'}
            fill
            sizes="(max-width: 768px) 100vw, 50vw"
            className="object-cover"
            unoptimized
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-indigo-600/20 via-purple-600/10 to-slate-900" />
        )}
                <div className="absolute inset-0 flex items-center justify-center">
                    <div className="h-20 w-20 rounded-full bg-white/10 backdrop-blur-xl flex items-center justify-center border border-white/20 group-hover:scale-110 transition-transform duration-300">
                        <Play className="h-8 w-8 text-white ml-1" />
                    </div>
                </div>
                {label && (
                    <span className="absolute bottom-4 left-4 text-white/70 text-sm">{label}</span>
                )}
            </div>
        );
    }

    return (
        <div className="aspect-video">
            <video
                src={src}
                controls
                autoPlay
                className="w-full h-full object-cover"
                poster={poster}
            />
        </div>
    );
}

function ImageDisplay({ src, label }: { src: string; label?: string }) {
  return (
    <div className="aspect-video relative">
      <Image
        src={src}
        alt={label ?? 'Screenshot'}
        fill
        sizes="(max-width: 768px) 100vw, 50vw"
        className="object-cover"
        unoptimized
      />
      {label && (
        <span className="absolute bottom-4 left-4 text-white/70 text-sm bg-black/40 px-2 py-1 rounded">{label}</span>
      )}
    </div>
  );
}

function MediaCard({ item, browserChrome, chromeTitle }: { item: MediaItem; browserChrome: boolean; chromeTitle?: string }) {
    const content = !item.src ? (
        <MediaPlaceholder type={item.type} label={item.label} />
    ) : item.type === 'video' ? (
        <VideoPlayer src={item.src} poster={item.poster} label={item.label} />
    ) : (
        <ImageDisplay src={item.src} label={item.label} />
    );

    if (browserChrome) {
        return <BrowserChrome title={chromeTitle ?? item.label}>{content}</BrowserChrome>;
    }

    return (
        <div className="rounded-2xl overflow-hidden border border-slate-200 dark:border-white/10 shadow-2xl">
            {content}
        </div>
    );
}

export function MediaShowcase({
    title,
    subtitle,
    media,
    className,
    browserChrome = true,
}: MediaShowcaseProps) {
    const isSingle = media.length === 1;

    return (
        <section className={`py-24 relative snap-start ${className ?? ''}`}>
            <AnimatedContainer className="container mx-auto px-6">
                {(title || subtitle) && (
                    <div className="text-center mb-12">
                        {title && (
                            <h2 className="text-3xl md:text-5xl font-bold heading-section mb-4 text-slate-900 dark:text-white">
                                {title}
                            </h2>
                        )}
                        {subtitle && (
                            <p className="text-xl text-slate-600 dark:text-gray-400">{subtitle}</p>
                        )}
                    </div>
                )}

                {isSingle ? (
                    <div className="max-w-4xl mx-auto scroll-scale-in">
                        <MediaCard
                            item={media[0]}
                            browserChrome={browserChrome}
                            chromeTitle={`Iudex — ${media[0].label ?? 'Plataforma Juridica com IA'}`}
                        />
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-6xl mx-auto">
                        {media.map((item, i) => (
                            <div key={i} className={`scroll-fade-up scroll-stagger-${Math.min(i + 1, 4)}`}>
                                <MediaCard item={item} browserChrome={browserChrome} />
                                {item.label && !item.src && (
                                    <p className="text-center text-sm text-slate-500 dark:text-gray-400 mt-3">{item.label}</p>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </AnimatedContainer>
        </section>
    );
}
