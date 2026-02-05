'use client';

import React, { useMemo } from 'react';
import {
    SandpackProvider,
    SandpackLayout,
    SandpackCodeEditor,
    SandpackPreview as SandpackPreviewPanel,
    SandpackConsole,
} from '@codesandbox/sandpack-react';
import { type CodeArtifact } from '@/stores/canvas-store';
import { cn } from '@/lib/utils';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Monitor, Terminal } from 'lucide-react';

interface SandpackPreviewProps {
    artifact: CodeArtifact;
    showEditor?: boolean;
    height?: number;
    className?: string;
}

// Map artifact language to Sandpack template
const getTemplate = (language: string): 'react' | 'react-ts' | 'vanilla' | 'vanilla-ts' | 'vue' | 'vue-ts' | 'svelte' => {
    switch (language) {
        case 'tsx':
        case 'react':
            return 'react-ts';
        case 'jsx':
            return 'react';
        case 'vue':
            return 'vue';
        case 'svelte':
            return 'svelte';
        case 'typescript':
            return 'vanilla-ts';
        default:
            return 'vanilla';
    }
};

// Get main file name based on template
const getMainFile = (language: string): string => {
    switch (language) {
        case 'tsx':
        case 'react':
            return '/App.tsx';
        case 'jsx':
            return '/App.js';
        case 'vue':
            return '/src/App.vue';
        case 'svelte':
            return '/App.svelte';
        case 'typescript':
            return '/index.ts';
        default:
            return '/index.js';
    }
};

// Wrap code if needed for React components
const wrapCode = (code: string, language: string): string => {
    // If it's a React component without imports, add them
    if (['react', 'tsx', 'jsx'].includes(language)) {
        const hasReactImport = /import\s+.*?['"]react['"]/.test(code);
        const hasExport = /export\s+(default\s+)?/.test(code);

        let wrappedCode = code;

        if (!hasReactImport && (code.includes('useState') || code.includes('useEffect') || code.includes('<'))) {
            wrappedCode = `import React, { useState, useEffect, useCallback, useMemo } from 'react';\n\n${wrappedCode}`;
        }

        if (!hasExport && /function\s+\w+|const\s+\w+\s*=/.test(code)) {
            // Find the component name
            const match = code.match(/(?:function|const)\s+(\w+)/);
            if (match) {
                wrappedCode = `${wrappedCode}\n\nexport default ${match[1]};`;
            }
        }

        return wrappedCode;
    }

    return code;
};

export function SandpackPreview({
    artifact,
    showEditor = false,
    height = 400,
    className,
}: SandpackPreviewProps) {
    const template = getTemplate(artifact.language);
    const mainFile = getMainFile(artifact.language);
    const wrappedCode = wrapCode(artifact.code, artifact.language);

    const files = useMemo(() => {
        const baseFiles: Record<string, string> = {
            [mainFile]: wrappedCode,
        };

        // Add dependencies as package.json if specified
        if (artifact.dependencies?.length) {
            const deps: Record<string, string> = {};
            artifact.dependencies.forEach(dep => {
                deps[dep] = 'latest';
            });
            baseFiles['/package.json'] = JSON.stringify({
                dependencies: deps,
            }, null, 2);
        }

        return baseFiles;
    }, [mainFile, wrappedCode, artifact.dependencies]);

    return (
        <div className={cn("border rounded-lg overflow-hidden", className)}>
            <SandpackProvider
                template={template}
                files={files}
                theme="auto"
                options={{
                    recompileMode: 'delayed',
                    recompileDelay: 500,
                }}
            >
                <Tabs defaultValue="preview" className="w-full">
                    <div className="flex items-center justify-between px-2 py-1 bg-muted/30 border-b">
                        <TabsList className="h-7 bg-transparent p-0">
                            <TabsTrigger value="preview" className="h-6 px-2 text-xs data-[state=active]:bg-background">
                                <Monitor className="h-3 w-3 mr-1" />
                                Preview
                            </TabsTrigger>
                            <TabsTrigger value="console" className="h-6 px-2 text-xs data-[state=active]:bg-background">
                                <Terminal className="h-3 w-3 mr-1" />
                                Console
                            </TabsTrigger>
                        </TabsList>
                    </div>

                    <SandpackLayout>
                        {showEditor && (
                            <SandpackCodeEditor
                                showLineNumbers
                                showInlineErrors
                                style={{ height: `${height}px` }}
                            />
                        )}

                        <TabsContent value="preview" className="m-0">
                            <SandpackPreviewPanel
                                showOpenInCodeSandbox={false}
                                showRefreshButton
                                style={{ height: `${height}px` }}
                            />
                        </TabsContent>

                        <TabsContent value="console" className="m-0">
                            <SandpackConsole
                                style={{ height: `${height}px` }}
                            />
                        </TabsContent>
                    </SandpackLayout>
                </Tabs>
            </SandpackProvider>
        </div>
    );
}

export default SandpackPreview;
