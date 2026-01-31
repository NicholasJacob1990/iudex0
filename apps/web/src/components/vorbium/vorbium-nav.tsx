'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from './theme-toggle';

type VorbiumNavProps = {
  scrollRef: React.RefObject<HTMLElement>;
};

export function VorbiumNav({ scrollRef }: VorbiumNavProps) {
  const [hidden, setHidden] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  const lastScrollTopRef = useRef(0);
  const tickingRef = useRef(false);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    lastScrollTopRef.current = el.scrollTop;

    const onScroll = () => {
      if (tickingRef.current) return;
      tickingRef.current = true;

      requestAnimationFrame(() => {
        const st = el.scrollTop;
        const last = lastScrollTopRef.current;
        const delta = st - last;

        // Keep the header visible near the top.
        if (st < 24) {
          setHidden(false);
          setScrolled(false);
        } else {
          setScrolled(true);

          // Small hysteresis so it doesn't jitter on trackpads.
          if (delta > 10) setHidden(true); // scrolling down
          if (delta < -8) setHidden(false); // scrolling up
        }

        lastScrollTopRef.current = st;
        tickingRef.current = false;
      });
    };

    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll as any);
  }, [scrollRef]);

  return (
    <nav
      className={[
        'fixed top-0 w-full z-50 transition-all duration-300',
        hidden ? '-translate-y-24 opacity-0 pointer-events-none' : 'translate-y-0 opacity-100',
        scrolled ? 'py-4 bg-white/80 dark:bg-[#0a0a0c]/80 backdrop-blur-xl border-b border-gray-200 dark:border-white/5 shadow-sm dark:shadow-none' : 'py-6',
      ].join(' ')}
    >
      <div className="container mx-auto px-6 flex items-center justify-between">
        <div className="flex items-center gap-12">
          <Link href="/"
            className={[
              'flex items-center gap-2 ',
            ].join(' ')}
          >
            <div className="h-6 w-6 rounded-lg bg-indigo-600 flex items-center justify-center">
              <span className="font-bold text-white text-xs">V</span>
            </div>
            <span className="text-lg font-medium tracking-tight text-slate-900 dark:text-white">Vorbium</span>
          </Link>

          <div className="hidden lg:flex items-center gap-6">
            <Link href="/platform" className="text-sm text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-white transition-colors">Platform</Link>
            <Link href="/assistant" className="text-sm text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-white transition-colors">Assistant</Link>
            <Link href="/research" className="text-sm text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-white transition-colors">Research</Link>
            <Link href="/workflows" className="text-sm text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-white transition-colors">Workflows</Link>
            <Link href="/collaboration" className="text-sm text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-white transition-colors">Collaboration</Link>
            <Link href="/customers" className="text-sm text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-white transition-colors">Customers</Link>
            <Link href="/security" className="text-sm text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-white transition-colors">Security</Link>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <Link href="/resources" className="hidden md:block text-sm text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">Resources</Link>
          <Link href="/about" className="hidden md:block text-sm text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors mr-2">About</Link>

          <ThemeToggle />

          <Link href="/login" className="hidden md:block">
            <span className="text-sm text-gray-600 dark:text-white transition-colors px-2 hover:text-gray-900 dark:hover:text-gray-300">Login</span>
          </Link>
          <Link href="/demo">
            <Button size="sm" className="rounded-md bg-indigo-600 text-white hover:bg-indigo-700 dark:hover:bg-indigo-700 font-medium px-4">
              Solicitar demo
            </Button>
          </Link>
        </div>
      </div>
    </nav>
  );
}
