import Link from 'next/link';
import React from 'react';

export function Footer() {
    return (
        <footer className="border-t border-slate-200 dark:border-white/5 bg-slate-50 dark:bg-[#050507] pt-24 pb-12 snap-start">
            <div className="container mx-auto px-6">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-12 mb-16">
                    <div className="md:col-span-1">
                        <div className="flex items-center gap-2 mb-6">
                            <div className="h-8 w-8 rounded-lg bg-indigo-600/20 flex items-center justify-center">
                                <span className="font-bold text-indigo-600 dark:text-indigo-500">V</span>
                            </div>
                            <span className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">Vorbium</span>
                        </div>
                        <p className="text-slate-600 dark:text-gray-500 text-sm leading-relaxed">
                            Sistema jurídico agentivo com governança, auditabilidade e supervisão humana por padrão.
                        </p>
                    </div>

                    <div>
                        <h4 className="text-slate-900 dark:text-white font-semibold mb-6">Plataforma</h4>
                        <div className="flex flex-col gap-4 text-sm text-slate-600 dark:text-gray-400">
                            <Link href="/assistant" className="hover:text-indigo-600 dark:hover:text-vorbium-accent transition-colors">Assistant</Link>
                            <Link href="/research" className="hover:text-indigo-600 dark:hover:text-vorbium-accent transition-colors">Research</Link>
                            <Link href="/workflows" className="hover:text-indigo-600 dark:hover:text-vorbium-accent transition-colors">Workflows</Link>
                            <Link href="/collaboration" className="hover:text-indigo-600 dark:hover:text-vorbium-accent transition-colors">Collaboration</Link>
                        </div>
                    </div>

                    <div>
                        <h4 className="text-slate-900 dark:text-white font-semibold mb-6">Institucional</h4>
                        <div className="flex flex-col gap-4 text-sm text-slate-600 dark:text-gray-400">
                            <Link href="/customers" className="hover:text-indigo-600 dark:hover:text-vorbium-accent transition-colors">Clientes</Link>
                            <Link href="/security" className="hover:text-indigo-600 dark:hover:text-vorbium-accent transition-colors">Segurança</Link>
                            <Link href="/about" className="hover:text-indigo-600 dark:hover:text-vorbium-accent transition-colors">Sobre nós</Link>
                            <Link href="/resources" className="hover:text-indigo-600 dark:hover:text-vorbium-accent transition-colors">Resources</Link>
                        </div>
                    </div>

                    <div>
                        <h4 className="text-slate-900 dark:text-white font-semibold mb-6">Contato</h4>
                        <div className="flex flex-col gap-4 text-sm text-slate-600 dark:text-gray-400">
                            <Link href="#" className="hover:text-indigo-600 dark:hover:text-vorbium-accent transition-colors">Suporte</Link>
                            <Link href="#" className="hover:text-indigo-600 dark:hover:text-vorbium-accent transition-colors">Vendas</Link>
                            <Link href="#" className="hover:text-indigo-600 dark:hover:text-vorbium-accent transition-colors">LinkedIn</Link>
                        </div>
                    </div>
                </div>

                <div className="pt-8 border-t border-slate-200 dark:border-white/5 flex flex-col md:flex-row justify-between items-center gap-4">
                    <p className="text-xs text-slate-500 dark:text-gray-700">© 2026 Vorbium Inc. Todos os direitos reservados.</p>
                    <div className="flex gap-6 text-xs text-slate-500 dark:text-gray-600">
                        <Link href="#" className="hover:text-slate-900 dark:hover:text-gray-400">Termos de Uso</Link>
                        <Link href="#" className="hover:text-slate-900 dark:hover:text-gray-400">Privacidade</Link>
                        <Link href="#" className="hover:text-slate-900 dark:hover:text-gray-400">Segurança</Link>
                    </div>
                </div>
            </div>
        </footer>
    );
}
