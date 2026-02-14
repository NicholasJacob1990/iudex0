'use client';

import Link from 'next/link';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Feather, Upload, Gavel } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { MotionDiv, fadeUp } from '@/components/ui/motion';
import { StaggerContainer } from '@/components/ui/animated-container';

const iconMap: Record<string, LucideIcon> = {
  Feather,
  Upload,
  Gavel,
};

const quickActions = [
  {
    id: 'action-1',
    title: 'Nova Minuta',
    description: 'Gere petições completas com revisão cruzada',
    icon: 'Feather',
    href: '/minuta',
  },
  {
    id: 'action-2',
    title: 'Importar Documentos',
    description: 'Junte PDFs, DOCX, ZIP e imagens',
    icon: 'Upload',
    href: '/documents',
  },
  {
    id: 'action-3',
    title: 'Buscar Jurisprudência STF',
    description: 'Entregue precedentes com repercussão geral',
    icon: 'Gavel',
    href: '/jurisprudence',
  },
];

export function QuickActions() {
  return (
    <StaggerContainer as="section" className="grid gap-4 md:grid-cols-3">
      {quickActions.map((action) => {
        const Icon = iconMap[action.icon] ?? Feather;
        return (
          <MotionDiv
            key={action.id}
            variants={fadeUp}
            className="group card-premium glow-hover rounded-3xl border border-black/[0.06] bg-white/80 p-5 shadow-soft backdrop-blur-sm dark:border-white/[0.06] dark:bg-white/[0.04]"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="font-display text-lg text-foreground">{action.title}</p>
                <p className="text-sm text-muted-foreground">{action.description}</p>
              </div>
              <span
                className={cn(
                  'flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/10 to-rose-100 text-primary'
                )}
              >
                <Icon className="h-5 w-5 group-hover:rotate-12 transition-transform duration-300" />
              </span>
            </div>
            <Button asChild className="mt-4 rounded-2xl bg-primary text-primary-foreground shadow-soft">
              <Link href={action.href}>Acessar</Link>
            </Button>
          </MotionDiv>
        );
      })}
    </StaggerContainer>
  );
}
