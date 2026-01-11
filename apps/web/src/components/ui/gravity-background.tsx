'use client';

import React, { useEffect, useRef } from 'react';

interface Particle {
    x: number;
    y: number;
    vx: number;
    vy: number;
    size: number;
    color: string;
    baseX: number;
    baseY: number;
    density: number;
}

export function GravityBackground() {
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        let animationFrameId: number;
        let particles: Particle[] = [];

        const mouse = {
            x: 0,
            y: 0,
            radius: 150,
        };

        const handleResize = () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            initParticles();
        };

        const handleMouseMove = (e: MouseEvent) => {
            mouse.x = e.x;
            mouse.y = e.y;
        };

        const initParticles = () => {
            particles = [];
            const numberOfParticles = Math.floor((canvas.width * canvas.height) / 9000);

            for (let i = 0; i < numberOfParticles; i++) {
                const size = Math.random() * 2 + 1;
                const x = Math.random() * (canvas.width - size * 2) + size * 2;
                const y = Math.random() * (canvas.height - size * 2) + size * 2;
                const directionX = Math.random() * 2 - 1;
                const directionY = Math.random() * 2 - 1;

                // Colors: Indigo, Purple, and White with low opacity
                const colors = [
                    'rgba(99, 102, 241, 0.3)', // Indigo
                    'rgba(168, 85, 247, 0.3)', // Purple
                    'rgba(255, 255, 255, 0.1)'  // White
                ];
                const color = colors[Math.floor(Math.random() * colors.length)];

                particles.push({
                    x,
                    y,
                    vx: directionX,
                    vy: directionY,
                    size,
                    color,
                    baseX: x,
                    baseY: y,
                    density: Math.random() * 30 + 1,
                });
            }
        };

        const animate = () => {
            if (!ctx || !canvas) return;
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            for (let i = 0; i < particles.length; i++) {
                let p = particles[i];

                // Movement
                p.x += p.vx;
                p.y += p.vy;

                // Mouse interaction (Repulsion/Gravity effect)
                const dx = mouse.x - p.x;
                const dy = mouse.y - p.y;
                const distance = Math.sqrt(dx * dx + dy * dy);

                if (distance < mouse.radius) {
                    const forceDirectionX = dx / distance;
                    const forceDirectionY = dy / distance;
                    const maxDistance = mouse.radius;
                    const force = (maxDistance - distance) / maxDistance;
                    const directionX = forceDirectionX * force * p.density;
                    const directionY = forceDirectionY * force * p.density;

                    // Repulsion
                    p.x -= directionX;
                    p.y -= directionY;
                } else {
                    // Return to base speed/direction if not affected
                    if (p.x !== p.baseX) {
                        const dx = p.x - p.baseX;
                        p.x -= dx / 10;
                    }
                    if (p.y !== p.baseY) {
                        const dy = p.y - p.baseY;
                        p.y -= dy / 10;
                    }
                }

                // Bounce off edges
                if (p.x < 0 || p.x > canvas.width) p.vx = -p.vx;
                if (p.y < 0 || p.y > canvas.height) p.vy = -p.vy;

                // Draw
                ctx.beginPath();
                ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                ctx.fillStyle = p.color;
                ctx.fill();
            }

            // Connect particles
            connect();

            animationFrameId = requestAnimationFrame(animate);
        };

        const connect = () => {
            for (let a = 0; a < particles.length; a++) {
                for (let b = a; b < particles.length; b++) {
                    const dx = particles[a].x - particles[b].x;
                    const dy = particles[a].y - particles[b].y;
                    const distance = Math.sqrt(dx * dx + dy * dy);

                    if (distance < 100) {
                        const opacityValue = 1 - distance / 100;
                        ctx.strokeStyle = `rgba(99, 102, 241, ${opacityValue * 0.15})`;
                        ctx.lineWidth = 1;
                        ctx.beginPath();
                        ctx.moveTo(particles[a].x, particles[a].y);
                        ctx.lineTo(particles[b].x, particles[b].y);
                        ctx.stroke();
                    }
                }
            }
        };

        window.addEventListener('resize', handleResize);
        window.addEventListener('mousemove', handleMouseMove);

        handleResize();
        animate();

        return () => {
            window.removeEventListener('resize', handleResize);
            window.removeEventListener('mousemove', handleMouseMove);
            cancelAnimationFrame(animationFrameId);
        };
    }, []);

    return (
        <canvas
            ref={canvasRef}
            className="fixed inset-0 w-full h-full pointer-events-none z-0"
            style={{ background: 'transparent' }}
        />
    );
}
