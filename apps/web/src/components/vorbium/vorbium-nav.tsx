'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, Menu, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from './theme-toggle';

/* ------------------------------------------------------------------ */
/*  Data                                                               */
/* ------------------------------------------------------------------ */

interface NavDropdownItem {
  label: string;
  href: string;
  description: string;
}

interface NavDropdownGroup {
  label: string;
  items: NavDropdownItem[];
}

const PLATFORM_ITEMS: NavDropdownItem[] = [
  {
    label: 'Assistente',
    href: '/assistant',
    description: 'Interface de raciocinio juridico com IA multi-agente.',
  },
  {
    label: 'Pesquisa',
    href: '/research',
    description: 'Pesquisa profunda em legislacao, jurisprudencia e doutrina.',
  },
  {
    label: 'Workflows',
    href: '/workflows',
    description: 'Automacao baseada em logica juridica executavel.',
  },
  {
    label: 'Colaboracao',
    href: '/collaboration',
    description: 'Construa documentos juridicos em equipe.',
  },
];

const EMPRESA_ITEMS: NavDropdownItem[] = [
  {
    label: 'Clientes',
    href: '/customers',
    description: 'Quem confia na VORBIUM.',
  },
  {
    label: 'Seguranca',
    href: '/security',
    description: 'Seus dados, protegidos.',
  },
];

const NAV_GROUPS: NavDropdownGroup[] = [
  { label: 'Plataforma', items: PLATFORM_ITEMS },
  { label: 'Empresa', items: EMPRESA_ITEMS },
];

/* ------------------------------------------------------------------ */
/*  Dropdown panel (desktop)                                           */
/* ------------------------------------------------------------------ */

function DropdownPanel({ items, onClose }: { items: NavDropdownItem[]; onClose: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className="absolute left-0 top-full pt-2 z-50"
    >
      <div className="min-w-[340px] rounded-xl border border-gray-200 bg-white/95 p-2 shadow-xl backdrop-blur-xl dark:border-white/10 dark:bg-[#111114]/95">
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            onClick={onClose}
            className="group flex flex-col gap-0.5 rounded-lg px-3.5 py-2.5 transition-colors hover:bg-gray-100 dark:hover:bg-white/5"
          >
            <span className="text-sm font-medium text-gray-900 dark:text-white">
              {item.label}
            </span>
            <span className="text-xs leading-relaxed text-gray-500 dark:text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-300">
              {item.description}
            </span>
          </Link>
        ))}
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Desktop nav trigger                                                */
/* ------------------------------------------------------------------ */

function NavGroupTrigger({
  group,
  isOpen,
  onOpen,
  onClose,
}: {
  group: NavDropdownGroup;
  isOpen: boolean;
  onOpen: () => void;
  onClose: () => void;
}) {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleEnter = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(onOpen, 120);
  };

  const handleLeave = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(onClose, 200);
  };

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return (
    <div className="relative" onMouseEnter={handleEnter} onMouseLeave={handleLeave}>
      <button
        type="button"
        className="flex items-center gap-1 text-sm text-gray-500 transition-colors hover:text-indigo-600 dark:text-gray-400 dark:hover:text-white"
      >
        {group.label}
        <ChevronDown
          className={[
            'h-3.5 w-3.5 transition-transform duration-200',
            isOpen ? 'rotate-180' : '',
          ].join(' ')}
        />
      </button>

      <AnimatePresence>
        {isOpen && <DropdownPanel items={group.items} onClose={onClose} />}
      </AnimatePresence>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Mobile menu                                                        */
/* ------------------------------------------------------------------ */

function MobileMenu({ onClose }: { onClose: () => void }) {
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

  const toggleGroup = (label: string) => {
    setExpandedGroup((prev) => (prev === label ? null : label));
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className="fixed inset-0 top-0 z-40 flex flex-col bg-white dark:bg-[#0a0a0c]"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-5">
        <Link href="/" onClick={onClose} className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-indigo-600">
            <span className="text-xs font-bold text-white">V</span>
          </div>
          <span className="text-lg font-medium tracking-tight text-slate-900 dark:text-white">
            Vorbium
          </span>
        </Link>
        <button type="button" onClick={onClose} className="p-1 text-gray-500 dark:text-gray-400">
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Links */}
      <div className="flex-1 overflow-y-auto px-6 pb-8">
        {/* Standalone link */}
        <Link
          href="/platform"
          onClick={onClose}
          className="block py-3 text-sm font-medium text-gray-900 dark:text-white"
        >
          Plataforma Overview
        </Link>

        <div className="my-2 border-t border-gray-100 dark:border-white/5" />

        {/* Grouped links */}
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <button
              type="button"
              onClick={() => toggleGroup(group.label)}
              className="flex w-full items-center justify-between py-3 text-sm font-medium text-gray-900 dark:text-white"
            >
              {group.label}
              <ChevronDown
                className={[
                  'h-4 w-4 text-gray-400 transition-transform duration-200',
                  expandedGroup === group.label ? 'rotate-180' : '',
                ].join(' ')}
              />
            </button>

            <AnimatePresence>
              {expandedGroup === group.label && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2, ease: 'easeOut' }}
                  className="overflow-hidden"
                >
                  <div className="pb-2 pl-3">
                    {group.items.map((item) => (
                      <Link
                        key={item.href}
                        href={item.href}
                        onClick={onClose}
                        className="block rounded-lg px-3 py-2.5 transition-colors hover:bg-gray-50 dark:hover:bg-white/5"
                      >
                        <span className="block text-sm text-gray-800 dark:text-gray-200">
                          {item.label}
                        </span>
                        <span className="block text-xs text-gray-500 dark:text-gray-400">
                          {item.description}
                        </span>
                      </Link>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="my-1 border-t border-gray-100 dark:border-white/5" />
          </div>
        ))}

        {/* Extra standalone links */}
        <Link
          href="/resources"
          onClick={onClose}
          className="block py-3 text-sm text-gray-600 dark:text-gray-300"
        >
          Resources
        </Link>
        <Link
          href="/about"
          onClick={onClose}
          className="block py-3 text-sm text-gray-600 dark:text-gray-300"
        >
          About
        </Link>

        <div className="my-4 border-t border-gray-100 dark:border-white/5" />

        <div className="flex flex-col gap-3">
          <Link href="/login" onClick={onClose}>
            <Button variant="outline" className="w-full">
              Login
            </Button>
          </Link>
          <Link href="/demo" onClick={onClose}>
            <Button className="w-full rounded-md bg-indigo-600 text-white hover:bg-indigo-700">
              Solicitar demo
            </Button>
          </Link>
        </div>
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main nav                                                           */
/* ------------------------------------------------------------------ */

type VorbiumNavProps = {
  scrollRef: React.RefObject<HTMLElement>;
};

export function VorbiumNav({ scrollRef }: VorbiumNavProps) {
  const [hidden, setHidden] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  const lastScrollTopRef = useRef(0);
  const tickingRef = useRef(false);

  /* Scroll hide/show --------------------------------------------- */
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

        if (st < 24) {
          setHidden(false);
          setScrolled(false);
        } else {
          setScrolled(true);
          if (delta > 10) setHidden(true);
          if (delta < -8) setHidden(false);
        }

        lastScrollTopRef.current = st;
        tickingRef.current = false;
      });
    };

    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll as EventListener);
  }, [scrollRef]);

  /* Close dropdown on scroll ------------------------------------- */
  useEffect(() => {
    if (!openDropdown) return;
    const el = scrollRef.current;
    if (!el) return;

    const close = () => setOpenDropdown(null);
    el.addEventListener('scroll', close, { passive: true });
    return () => el.removeEventListener('scroll', close as EventListener);
  }, [openDropdown, scrollRef]);

  const handleDropdownOpen = useCallback((label: string) => setOpenDropdown(label), []);
  const handleDropdownClose = useCallback(() => setOpenDropdown(null), []);

  return (
    <>
      <nav
        className={[
          'fixed top-0 w-full z-50 transition-all duration-300',
          hidden
            ? '-translate-y-24 opacity-0 pointer-events-none'
            : 'translate-y-0 opacity-100',
          scrolled
            ? 'py-4 bg-white/80 dark:bg-[#0a0a0c]/80 backdrop-blur-xl border-b border-gray-200 dark:border-white/5 shadow-sm dark:shadow-none'
            : 'py-6',
        ].join(' ')}
      >
        <div className="container mx-auto flex items-center justify-between px-6">
          {/* Left: logo + nav groups */}
          <div className="flex items-center gap-12">
            <Link href="/" className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-indigo-600">
                <span className="text-xs font-bold text-white">V</span>
              </div>
              <span className="text-lg font-medium tracking-tight text-slate-900 dark:text-white">
                Vorbium
              </span>
            </Link>

            {/* Desktop links */}
            <div className="hidden items-center gap-6 lg:flex">
              {/* Standalone: Plataforma overview */}
              <Link
                href="/platform"
                className="text-sm text-gray-500 transition-colors hover:text-indigo-600 dark:text-gray-400 dark:hover:text-white"
              >
                Plataforma
              </Link>

              {/* Dropdown groups */}
              {NAV_GROUPS.map((group) => (
                <NavGroupTrigger
                  key={group.label}
                  group={group}
                  isOpen={openDropdown === group.label}
                  onOpen={() => handleDropdownOpen(group.label)}
                  onClose={handleDropdownClose}
                />
              ))}
            </div>
          </div>

          {/* Right: extra links + actions */}
          <div className="flex items-center gap-4">
            <Link
              href="/resources"
              className="hidden text-sm text-gray-500 dark:text-gray-400 transition-colors hover:text-gray-900 dark:hover:text-white md:block"
            >
              Resources
            </Link>
            <Link
              href="/about"
              className="mr-2 hidden text-sm text-gray-500 dark:text-gray-400 transition-colors hover:text-gray-900 dark:hover:text-white md:block"
            >
              About
            </Link>

            <ThemeToggle />

            <Link href="/login" className="hidden md:block">
              <span className="px-2 text-sm text-gray-600 transition-colors hover:text-gray-900 dark:text-white dark:hover:text-gray-300">
                Login
              </span>
            </Link>
            <Link href="/demo">
              <Button
                size="sm"
                className="rounded-md bg-indigo-600 px-4 font-medium text-white hover:bg-indigo-700 dark:hover:bg-indigo-700"
              >
                Solicitar demo
              </Button>
            </Link>

            {/* Mobile hamburger */}
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              className="p-1 text-gray-500 dark:text-gray-400 lg:hidden"
            >
              <Menu className="h-5 w-5" />
            </button>
          </div>
        </div>
      </nav>

      {/* Mobile overlay */}
      <AnimatePresence>
        {mobileOpen && <MobileMenu onClose={() => setMobileOpen(false)} />}
      </AnimatePresence>
    </>
  );
}
