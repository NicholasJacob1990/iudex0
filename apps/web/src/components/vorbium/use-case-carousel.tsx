'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Briefcase, Gavel, Scale, Building2, FolderKanban, Search, ChevronLeft, ChevronRight } from 'lucide-react';

/* 
  Using CSS Scroll Snap for the carousel experience.
  Does not require JS for the snapping logic.
*/

const items = [
    {
        title: "Due diligence transacional",
        role: "M&A / Contratos",
        desc: "Compare clausulas e pontos-chave em centenas de documentos com tabelas estruturadas e revisao guiada.",
        icon: <Briefcase className="w-8 h-8 text-indigo-400" />,
        color: "from-indigo-900/40 to-indigo-900/10"
    },
    {
        title: "Preparacao de contencioso",
        role: "Litigio",
        desc: "Organize fatos, evidencias e riscos com consultas sobre o acervo inteiro e citacoes rastreaveis.",
        icon: <Gavel className="w-8 h-8 text-amber-400" />,
        color: "from-amber-900/40 to-amber-900/10"
    },
    {
        title: "Gestao de conhecimento interno",
        role: "Know-how",
        desc: "Centralize modelos, memorandos e precedentes para gerar trabalho consistente, mesmo com rotatividade de time.",
        icon: <FolderKanban className="w-8 h-8 text-emerald-400" />,
        color: "from-emerald-900/40 to-emerald-900/10"
    },
    {
        title: "Extracao de precedentes",
        role: "Pesquisa",
        desc: "Isole trechos relevantes, tese, fundamentacao e citacoes para acelerar briefs e anotacoes.",
        icon: <Search className="w-8 h-8 text-sky-300" />,
        color: "from-sky-900/40 to-sky-900/10"
    },
    {
        title: "Triagem e organizacao de discovery",
        role: "Volume alto",
        desc: "Classifique, agrupe e revise grandes lotes com criterios claros e controle de acesso por projeto.",
        icon: <Building2 className="w-8 h-8 text-purple-300" />,
        color: "from-purple-900/40 to-purple-900/10"
    },
    {
        title: "Revisao colaborativa",
        role: "Time + parceiros",
        desc: "Compartilhe vaults e tabelas de revisao com permissao granular, mantendo governanca e trilha de auditoria.",
        icon: <Scale className="w-8 h-8 text-teal-300" />,
        color: "from-teal-900/40 to-teal-900/10"
    }
];

export function UseCaseCarousel() {
    const scrollerRef = useRef<HTMLDivElement>(null);
    const dragStateRef = useRef<{ startX: number; scrollLeft: number; pointerId: number | null }>({
        startX: 0,
        scrollLeft: 0,
        pointerId: null,
    });
    const isDraggingRef = useRef(false);
    const [isDragging, setIsDragging] = useState(false);
    const [canScrollLeft, setCanScrollLeft] = useState(false);
    const [canScrollRight, setCanScrollRight] = useState(false);

    useEffect(() => {
        const el = scrollerRef.current;
        if (!el) return;

        const updateScrollButtons = () => {
            const maxScrollLeft = el.scrollWidth - el.clientWidth;
            setCanScrollLeft(el.scrollLeft > 8);
            setCanScrollRight(el.scrollLeft < maxScrollLeft - 8);
        };

        const onWheel = (e: WheelEvent) => {
            // Allow normal trackpad horizontal scrolling (deltaX) and shift+wheel.
            if (e.shiftKey) return;
            // Only hijack when vertical wheel is dominant and the carousel can scroll horizontally.
            if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
            if (el.scrollWidth <= el.clientWidth + 1) return;

            el.scrollLeft += e.deltaY;
            e.preventDefault();
        };

        // Needs passive:false so preventDefault works (avoids vertical page scroll while wheeling over the carousel).
        el.addEventListener('wheel', onWheel, { passive: false });
        el.addEventListener('scroll', updateScrollButtons, { passive: true });
        window.addEventListener('resize', updateScrollButtons);
        updateScrollButtons();

        return () => {
            el.removeEventListener('wheel', onWheel as any);
            el.removeEventListener('scroll', updateScrollButtons as any);
            window.removeEventListener('resize', updateScrollButtons);
        };
    }, []);

    const scrollByPage = (direction: 'left' | 'right') => {
        const el = scrollerRef.current;
        if (!el) return;
        const amount = Math.max(320, Math.floor(el.clientWidth * 0.85));
        el.scrollBy({ left: direction === 'left' ? -amount : amount, behavior: 'smooth' });
    };

    const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
        // Enable click-and-drag on desktop (trackpads already work, touch already swipes).
        if (e.pointerType !== 'mouse' || e.button !== 0) return;
        const el = scrollerRef.current;
        if (!el) return;

        el.setPointerCapture(e.pointerId);
        dragStateRef.current.pointerId = e.pointerId;
        dragStateRef.current.startX = e.clientX;
        dragStateRef.current.scrollLeft = el.scrollLeft;
        isDraggingRef.current = true;
        setIsDragging(true);
    };

    const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
        const el = scrollerRef.current;
        if (!el) return;
        if (!isDraggingRef.current) return;
        if (dragStateRef.current.pointerId !== e.pointerId) return;
        // Prevent text selection while dragging.
        e.preventDefault();

        const dx = e.clientX - dragStateRef.current.startX;
        el.scrollLeft = dragStateRef.current.scrollLeft - dx;
    };

    const endDrag = (e: React.PointerEvent<HTMLDivElement>) => {
        const el = scrollerRef.current;
        if (!el) return;
        if (dragStateRef.current.pointerId !== e.pointerId) return;
        dragStateRef.current.pointerId = null;
        isDraggingRef.current = false;
        setIsDragging(false);
    };

    return (
        <section className="py-24 bg-[#0a0a0c] text-white snap-start">
            <div className="container mx-auto px-6 mb-12">
                <div className="flex items-center gap-3 text-[10px] uppercase tracking-[0.3em] text-indigo-300/80 mb-4">
                    <span className="h-px w-10 bg-indigo-400/40" />
                    <span>Casos de uso</span>
                </div>
                <h2 className="text-3xl md:text-5xl font-bold mb-4">
                    Como equipes usam o <span className="text-indigo-500">Vault</span>
                </h2>
                <p className="text-gray-400 text-lg">Do transacional ao contencioso, com consistencia e controle.</p>
            </div>

            {/* 
        Scroll Container 
        Technique: scroll-snap-type: x mandatory 
        Use 'pb-12' to make room for scrollbar or indicators
      */}
            <div className="relative">
                <div
                    ref={scrollerRef}
                    className={`flex overflow-x-auto overflow-y-hidden snap-x snap-mandatory gap-6 px-6 pb-12 w-full no-scrollbar select-none ${isDragging ? 'cursor-grabbing' : 'cursor-grab'}`}
                    style={{ touchAction: 'pan-x' }}
                    onPointerDown={onPointerDown}
                    onPointerMove={onPointerMove}
                    onPointerUp={endDrag}
                    onPointerCancel={endDrag}
                    onPointerLeave={(e) => {
                        if (isDragging) endDrag(e);
                    }}
                >
                    {/* Spacer for left padding in carousel */}
                    <div className="shrink-0 w-0 md:w-12" />

                    {items.map((item, idx) => (
                        <div
                            key={idx}
                            className={`
              snap-center shrink-0 w-[85vw] md:w-[620px] h-[420px] 
              rounded-3xl border border-white/10 bg-gradient-to-br ${item.color} 
              p-12 flex flex-col justify-end relative overflow-hidden group
              hover:border-white/20 transition-all duration-500 hover:-translate-y-2
            `}
                        >
                            {/* Background Decoration */}
                            <div className="absolute top-0 right-0 p-12 opacity-10 group-hover:opacity-20 transition-opacity transform group-hover:scale-110 duration-700">
                                {React.cloneElement(item.icon as React.ReactElement, { className: "w-48 h-48" })}
                            </div>
                            <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none bg-gradient-to-t from-black/40 via-transparent to-transparent" />

                            <div className="relative z-10">
                                <div className="flex items-center gap-3 mb-4">
                                    <div className="p-3 rounded-full bg-white/5 backdrop-blur-md border border-white/10">
                                        {item.icon}
                                    </div>
                                    <span className="text-sm font-medium uppercase tracking-widest text-white/50">{item.role}</span>
                                </div>

                                <h3 className="text-3xl md:text-4xl font-bold mb-4 transform translate-y-0 transition-transform">{item.title}</h3>
                                <p className="text-xl text-gray-300 max-w-md">{item.desc}</p>
                            </div>
                        </div>
                    ))}

                    {/* Spacer for right padding */}
                    <div className="shrink-0 w-0 md:w-12" />
                </div>

                <div className="hidden md:flex items-center justify-between pointer-events-none absolute inset-y-0 left-0 right-0 px-4">
                    <button
                        type="button"
                        onClick={() => scrollByPage('left')}
                        disabled={!canScrollLeft}
                        className="pointer-events-auto h-10 w-10 rounded-full border border-white/10 bg-black/30 text-white/70 backdrop-blur transition hover:bg-black/45 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center"
                        aria-label="Anterior"
                    >
                        <ChevronLeft className="h-5 w-5" />
                    </button>
                    <button
                        type="button"
                        onClick={() => scrollByPage('right')}
                        disabled={!canScrollRight}
                        className="pointer-events-auto h-10 w-10 rounded-full border border-white/10 bg-black/30 text-white/70 backdrop-blur transition hover:bg-black/45 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center"
                        aria-label="Proximo"
                    >
                        <ChevronRight className="h-5 w-5" />
                    </button>
                </div>
            </div>

            <div className="mt-6 flex items-center justify-center gap-3 text-[11px] text-white/40">
                <span className="h-px w-8 bg-white/20" />
                <span>Arraste para explorar</span>
                <span className="h-px w-8 bg-white/20" />
            </div>

            <style jsx global>{`
        /* Hide scrollbar for Chrome, Safari and Opera */
        .no-scrollbar::-webkit-scrollbar {
          display: none;
        }
        /* Hide scrollbar for IE, Edge and Firefox */
        .no-scrollbar {
          -ms-overflow-style: none;  /* IE and Edge */
          scrollbar-width: none;  /* Firefox */
        }
      `}</style>
        </section>
    );
}
