'use client';

import { motion, useInView, type Variants } from 'framer-motion';
import { useRef, type ReactNode } from 'react';
import { fadeUp, smoothTransition } from './motion';
import { cn } from '@/lib/utils';

interface AnimatedContainerProps {
  children: ReactNode;
  className?: string;
  variants?: Variants;
  delay?: number;
  once?: boolean;
  as?: 'div' | 'section' | 'article' | 'li';
  margin?: string;
}

export function AnimatedContainer({
  children,
  className,
  variants = fadeUp,
  delay = 0,
  once = true,
  as = 'div',
  margin = '-80px',
}: AnimatedContainerProps) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once, margin: margin as `${number}px` });

  const Component = motion[as];

  return (
    <Component
      ref={ref}
      initial="hidden"
      animate={isInView ? 'visible' : 'hidden'}
      variants={variants}
      transition={{ ...smoothTransition, delay }}
      className={cn(className)}
    >
      {children}
    </Component>
  );
}

interface StaggerContainerProps {
  children: ReactNode;
  className?: string;
  once?: boolean;
  staggerDelay?: number;
  delayChildren?: number;
  as?: 'div' | 'section' | 'ul';
}

export function StaggerContainer({
  children,
  className,
  once = true,
  staggerDelay = 0.08,
  delayChildren = 0.1,
  as = 'div',
}: StaggerContainerProps) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once, margin: '-60px' as `${number}px` });

  const Component = motion[as];

  return (
    <Component
      ref={ref}
      initial="hidden"
      animate={isInView ? 'visible' : 'hidden'}
      variants={{
        hidden: {},
        visible: {
          transition: {
            staggerChildren: staggerDelay,
            delayChildren,
          },
        },
      }}
      className={cn(className)}
    >
      {children}
    </Component>
  );
}
