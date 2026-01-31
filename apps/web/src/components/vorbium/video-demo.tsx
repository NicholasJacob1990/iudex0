'use client';

import React, { useRef, useState } from 'react';
import { Play } from 'lucide-react';

export function VideoDemo() {
    const videoRef = useRef<HTMLVideoElement>(null);
    const [isPlaying, setIsPlaying] = useState(false);

    const handlePlay = () => {
        if (videoRef.current) {
            videoRef.current.play();
            setIsPlaying(true);
        }
    };

    return (
        <section className="py-32 bg-[#0a0a0c] relative snap-start">
            <div className="container mx-auto px-6">
                <div className="text-center mb-16 px-4">
                    <h2 className="text-3xl md:text-5xl font-bold mb-6 text-white">Tour rapido do <span className="text-indigo-500">Vault</span></h2>
                    <p className="text-gray-400 text-lg max-w-2xl mx-auto">
                        Veja como o Vorbium organiza grandes volumes, extrai informacoes e entrega respostas com referencias claras.
                    </p>
                </div>

                <div className="relative max-w-5xl mx-auto aspect-video rounded-2xl overflow-hidden border border-white/10 shadow-[0_0_100px_-20px_rgba(79,70,229,0.3)] bg-[#111]">
                    <div className="absolute top-6 left-6 z-20 flex items-center gap-2 rounded-full border border-white/10 bg-black/40 px-4 py-2 text-[11px] uppercase tracking-[0.3em] text-white/70 backdrop-blur">
                        <span className="relative inline-flex h-2 w-2">
                            <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping"></span>
                            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400"></span>
                        </span>
                        Walkthrough
                    </div>
                    <div className="absolute top-6 right-6 z-20 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-white/70 backdrop-blur">
                        Resposta com <span className="text-white">citacoes</span>
                    </div>

                    {/* Placeholder poster if no real video is available yet */}
                    <div className={`absolute inset-0 bg-gradient-to-br from-gray-900 to-black transition-opacity duration-500 flex items-center justify-center ${isPlaying ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}>
                        <div className="text-white/20 font-mono text-sm">
                            [VIDEO DEMONSTRAÇÃO - PLACEHOLDER]
                        </div>
                    </div>

                    <video
                        ref={videoRef}
                        className="w-full h-full object-cover"
                        controls={isPlaying}
                        // poster="/path/to/poster.jpg"
                        src="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
                    /* 
                       NOTE: Using a sample video for demonstration. 
                       Replace 'src' with actual product demo URL.
                    */
                    />

                    {!isPlaying && (
                        <button
                            onClick={handlePlay}
                            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-24 h-24 bg-white/10 hover:bg-white/20 backdrop-blur-md rounded-full flex items-center justify-center transition-all hover:scale-110 group border border-white/20"
                            aria-label="Reproduzir vídeo"
                        >
                            <Play className="w-8 h-8 text-white fill-white group-hover:text-indigo-400 group-hover:fill-indigo-400 transition-colors" />
                        </button>
                    )}
                </div>
            </div>
        </section>
    );
}
