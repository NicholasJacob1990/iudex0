import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
    DropdownMenuCheckboxItem,
    DropdownMenuRadioGroup,
    DropdownMenuRadioItem,
} from "@/components/ui/dropdown-menu";
import { useChatStore } from "@/stores/chat-store";
import { MODEL_REGISTRY, listModels, ModelId, getModelConfig } from "@/config/models";
import { ChevronDown, Sparkles, Scale, Zap, Columns2, PanelTop } from "lucide-react";
import Image from "next/image";

export function ModelSelector() {
    const {
        selectedModels,
        toggleModel,
        chatMode,
        setChatMode,
        showMultiModelComparator,
        setShowMultiModelComparator,
        autoConsolidate,
        setAutoConsolidate,
        multiModelView,
        setMultiModelView
    } = useChatStore();

    // Group models by provider for cleaner UI
    const openaiModels = listModels().filter(m => m.provider === 'openai');
    const anthropicModels = listModels().filter(m => m.provider === 'anthropic');
    const googleModels = listModels().filter(m => m.provider === 'google');
    const xaiModels = listModels().filter(m => m.provider === 'xai');
    const openrouterModels = listModels().filter(m => m.provider === 'openrouter');
    const internalModels = listModels().filter(m => m.provider === 'internal');

    // Helper to render icon
    const ModelIcon = ({ iconPath }: { iconPath: string }) => (
        <div className="relative w-4 h-4 mr-2 rounded-sm overflow-hidden bg-muted">
            <Image
                src={iconPath}
                alt=""
                fill
                className="object-cover"
                onError={(e) => {
                    // Fallback handled by parent if needed, or simple color block
                    // For now assuming icons exist in /logos/
                }}
            />
        </div>
    );

    const renderModelItem = (model: any) => {
        const isSelected = selectedModels.includes(model.id);
        return (
            <DropdownMenuCheckboxItem
                key={model.id}
                checked={isSelected}
                onCheckedChange={() => toggleModel(model.id)}
                className="flex items-center"
            >
                <ModelIcon iconPath={model.icon} />
                <div className="flex flex-col">
                    <span className="font-medium">{model.label}</span>
                    <span className="text-[10px] text-muted-foreground">{model.contextWindow / 1000}k ctx • {model.latencyTier} lat</span>
                </div>
            </DropdownMenuCheckboxItem>
        );
    };

    return (
        <div className="flex items-center gap-2">
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="h-8 gap-2">
                        {selectedModels.length === 0 ? "Selecionar Modelo" :
                            selectedModels.length === 1 ? (
                                <>
                                    <ModelIcon iconPath={getModelConfig(selectedModels[0] as ModelId)?.icon || ''} />
                                    {getModelConfig(selectedModels[0] as ModelId)?.label}
                                </>
                            ) : (
                                <>
                                    <Sparkles className="w-4 h-4 text-primary" />
                                    {selectedModels.length} Modelos
                                </>
                            )
                        }
                        <ChevronDown className="w-3 h-3 opacity-50" />
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-[280px]">
                    <div className="px-2 py-1.5 text-xs text-muted-foreground bg-muted/50">
                        Modo: {chatMode === 'standard' ? 'Padrão' : 'Multi-Modelo'}
                    </div>
                    {chatMode === 'multi-model' && (
                        <>
                            <DropdownMenuCheckboxItem
                                checked={showMultiModelComparator}
                                onCheckedChange={(v) => setShowMultiModelComparator(!!v)}
                                className="flex items-center gap-2"
                            >
                                <Columns2 className="h-3.5 w-3.5" />
                                Exibir comparador (Tabs)
                            </DropdownMenuCheckboxItem>
                            <DropdownMenuLabel className="pt-2 text-xs text-muted-foreground">Layout do comparador</DropdownMenuLabel>
                            <DropdownMenuRadioGroup
                                value={multiModelView}
                                onValueChange={(v) => setMultiModelView(v as any)}
                            >
                                <DropdownMenuRadioItem value="tabs" className="flex items-center gap-2">
                                    <PanelTop className="h-3.5 w-3.5" />
                                    Tabs
                                </DropdownMenuRadioItem>
                                <DropdownMenuRadioItem value="columns" className="flex items-center gap-2">
                                    <Columns2 className="h-3.5 w-3.5" />
                                    Lado a lado
                                </DropdownMenuRadioItem>
                            </DropdownMenuRadioGroup>
                            <DropdownMenuCheckboxItem
                                checked={autoConsolidate}
                                onCheckedChange={(v) => setAutoConsolidate(!!v)}
                                className="flex items-center gap-2"
                            >
                                <Sparkles className="h-3.5 w-3.5" />
                                Gerar consolidado automaticamente
                            </DropdownMenuCheckboxItem>
                        </>
                    )}
                    <DropdownMenuSeparator />

                    <DropdownMenuLabel>OpenAI</DropdownMenuLabel>
                    {openaiModels.map(renderModelItem)}

                    <DropdownMenuSeparator />
                    <DropdownMenuLabel>Anthropic</DropdownMenuLabel>
                    {anthropicModels.map(renderModelItem)}

                    <DropdownMenuSeparator />
                    <DropdownMenuLabel>Google</DropdownMenuLabel>
                    {googleModels.map(renderModelItem)}

                    {xaiModels.length > 0 && (
                        <>
                            <DropdownMenuSeparator />
                            <DropdownMenuLabel>xAI</DropdownMenuLabel>
                            {xaiModels.map(renderModelItem)}
                        </>
                    )}

                    {openrouterModels.length > 0 && (
                        <>
                            <DropdownMenuSeparator />
                            <DropdownMenuLabel>OpenRouter / Meta</DropdownMenuLabel>
                            {openrouterModels.map(renderModelItem)}
                        </>
                    )}

                    <DropdownMenuSeparator />
                    <DropdownMenuLabel>Interno</DropdownMenuLabel>
                    {internalModels.map(renderModelItem)}

                </DropdownMenuContent>
            </DropdownMenu>

            {/* Quick Toggles */}
            <div className="flex items-center bg-muted/50 rounded-lg p-0.5">
                <Button
                    variant={chatMode === 'standard' ? 'secondary' : 'ghost'}
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => setChatMode('standard')}
                    title="Modo Padrão (Único Modelo)"
                >
                    <Zap className="w-3.5 h-3.5" />
                </Button>
                <Button
                    variant={chatMode === 'multi-model' ? 'secondary' : 'ghost'}
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => setChatMode('multi-model')}
                    title="Modo Multi-Modelo (Paralelo)"
                >
                    <Scale className="w-3.5 h-3.5" />
                </Button>
            </div>
        </div>
    );
}
