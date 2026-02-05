'use client';

import { useEffect, useRef } from 'react';

/**
 * Hook that adds scroll-driven animation support as a fallback for browsers
 * that don't support CSS `animation-timeline: view()` (Safari, Firefox).
 *
 * Usage:
 * 1. Add CSS scroll-driven classes (scroll-fade-up, scroll-scale-in, etc.) to elements
 * 2. Call useScrollAnimationFallback() once in a layout or page component
 * 3. In supported browsers (Chrome/Edge), CSS handles animations natively
 * 4. In unsupported browsers, IntersectionObserver adds `.in-view` class
 *
 * For unsupported browsers, combine with CSS:
 * ```css
 * @supports not (animation-timeline: view()) {
 *   .scroll-fade-up { opacity: 0; transform: translateY(40px); transition: all 0.6s ease-out; }
 *   .scroll-fade-up.in-view { opacity: 1; transform: translateY(0); }
 * }
 * ```
 */
export function useScrollAnimationFallback() {
  const observerRef = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    // Check if native scroll-driven animations are supported
    const supportsScrollTimeline = CSS.supports('animation-timeline', 'view()');
    if (supportsScrollTimeline) return; // Native CSS handles it

    // Fallback: IntersectionObserver adds .in-view class
    const selector = [
      '.scroll-fade-up',
      '.scroll-scale-in',
      '.scroll-blur-in',
      '.scroll-slide-left',
      '.scroll-slide-right',
    ].join(',');

    observerRef.current = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('in-view');
          }
        });
      },
      { threshold: 0.15, rootMargin: '0px 0px -50px 0px' }
    );

    const elements = document.querySelectorAll(selector);
    elements.forEach((el) => observerRef.current?.observe(el));

    return () => {
      observerRef.current?.disconnect();
    };
  }, []);
}
