import { FileText, Clock, Lock, ExternalLink } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || '/api';

interface SharedDocument {
    id: string;
    name: string;
    content?: string;
    extracted_text?: string;
    type: string;
    created_at: string;
    access_level: string;
}

async function getSharedDocument(token: string): Promise<SharedDocument | null> {
    try {
        const res = await fetch(`${API_URL}/documents/share/${token}`, {
            cache: 'no-store',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!res.ok) {
            console.error('Share fetch error:', res.status);
            return null;
        }

        return res.json();
    } catch (error) {
        console.error('Share fetch error:', error);
        return null;
    }
}

export default async function SharePage({ params }: { params: { token: string } }) {
    const doc = await getSharedDocument(params.token);

    if (!doc) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4">
                <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 max-w-md text-center border border-white/20">
                    <div className="bg-red-500/20 p-4 rounded-full w-16 h-16 mx-auto mb-4 flex items-center justify-center">
                        <Lock className="h-8 w-8 text-red-400" />
                    </div>
                    <h1 className="text-2xl font-bold text-white mb-2">Link Inválido</h1>
                    <p className="text-slate-400">
                        Este documento não existe, o link expirou ou foi desativado pelo proprietário.
                    </p>
                </div>
            </div>
        );
    }

    const displayContent = doc.content || doc.extracted_text || "Documento sem conteúdo de texto disponível.";
    const rawContent = String(displayContent || '').trim();
    const looksLikeHtml = /<(p|h1|h2|h3|h4|h5|h6|div|ul|ol|li|table|thead|tbody|tr|td|th|blockquote|strong|em|span)(\s|>)/i.test(
        rawContent
    );
    const createdDate = new Date(doc.created_at).toLocaleDateString('pt-BR');

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100">
            {/* Header */}
            <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
                <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="bg-indigo-100 p-2 rounded-lg">
                            <FileText className="h-5 w-5 text-indigo-600" />
                        </div>
                        <div>
                            <h1 className="font-semibold text-slate-900 text-lg line-clamp-1">{doc.name}</h1>
                            <div className="flex items-center gap-2 text-xs text-slate-500">
                                <Clock className="h-3 w-3" />
                                <span>Compartilhado em {createdDate}</span>
                                <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 uppercase text-[10px] font-medium">
                                    {doc.access_level}
                                </span>
                            </div>
                        </div>
                    </div>
                    <a
                        href="https://iudex.ai"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700 font-medium"
                    >
                        Powered by Iudex
                        <ExternalLink className="h-3 w-3" />
                    </a>
                </div>
            </header>

            {/* Content */}
            <main className="max-w-4xl mx-auto px-4 py-8">
                <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                    <div className="p-6 md:p-8">
                        {looksLikeHtml ? (
                            <div className="editor-output" dangerouslySetInnerHTML={{ __html: rawContent }} />
                        ) : (
                            <pre className="editor-output whitespace-pre-wrap">{displayContent}</pre>
                        )}
                    </div>
                </div>

                <footer className="mt-8 text-center text-xs text-slate-500">
                    <p>Este documento foi compartilhado via Iudex. O link pode expirar.</p>
                </footer>
            </main>
        </div>
    );
}
