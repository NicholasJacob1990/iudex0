'use client';

import { useEffect, useMemo, useState, type ComponentType, type CSSProperties } from 'react';
import { useTheme } from 'next-themes';
import { useAuthStore, useUIStore } from '@/stores';
import { DEFAULT_CHAT_BG_TINT_DARK, DEFAULT_CHAT_BG_TINT_LIGHT, DEFAULT_TINT_MODE, type TintMode } from '@/stores/ui-store';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { MCPServersConfig } from '@/components/settings/mcp-servers-config';
import { DMSIntegrations } from '@/components/settings/dms-integrations';
import { buildGradientTrack, DARK_STOPS, LIGHT_STOPS, tintToColor } from '@/components/layout/top-nav';
import { getChatTintStyles } from '@/lib/chat-tint-styles';
import { apiClient } from '@/lib/api-client';
import { CheckCircle, CloudCog, Eye, EyeOff, Layers, Palette, Scale, Circle, Droplets, Sun, Moon, Monitor } from 'lucide-react';

type LangOption = 'pt-BR' | 'pt-PT' | 'en-US' | 'es-ES';

type ThemePreference = 'light' | 'dark' | 'system';

type MetricsSnapshot = {
  pointsAvailable: number | null;
  pointsUsed: number | null;
  pointsLimit: number | null;
  usdSpent: number | null;
  usdBudget: number | null;
};

const TINT_MODE_OPTIONS: Array<{
  value: TintMode;
  label: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
}> = [
  {
    value: 'layered',
    label: 'Layered',
    description: 'Mensagens destacadas e input/canvas no padrão.',
    icon: Layers,
  },
  {
    value: 'blended',
    label: 'Blended',
    description: 'Mescla suave entre mensagens e superfícies.',
    icon: Palette,
  },
  {
    value: 'inset',
    label: 'Inset',
    description: 'Input/canvas mais profundos, mensagens mais claras.',
    icon: Droplets,
  },
  {
    value: 'uniform',
    label: 'Uniform',
    description: 'Toda área do chat no mesmo tom.',
    icon: Circle,
  },
];

const PRESET_BLUE_FILTER_LIGHT_TINT = 70; // ~#FAF8F5 (warm/off-white)

function pickNumber(data: any, paths: string[]): number | null {
  for (const path of paths) {
    const parts = path.split('.');
    let current: any = data;
    for (const part of parts) {
      if (current == null || typeof current !== 'object') {
        current = undefined;
        break;
      }
      current = current[part];
    }
    const value = Number(current);
    if (Number.isFinite(value)) return value;
  }
  return null;
}

function formatDate(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function formatNumber(value: number | null): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('pt-BR').format(value);
}

function formatCurrency(value: number | null): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
}

function extractMetrics(summary: any): MetricsSnapshot {
  return {
    pointsAvailable: pickNumber(summary, [
      'points_available',
      'summary.points_available',
      'wallet.points_available',
      'billing.points_available',
      'remaining_points',
    ]),
    pointsUsed: pickNumber(summary, [
      'points_used',
      'summary.points_used',
      'wallet.points_used',
      'billing.points_used',
      'usage.points_used',
    ]),
    pointsLimit: pickNumber(summary, [
      'points_limit',
      'summary.points_limit',
      'wallet.points_limit',
      'billing.points_limit',
      'usage.points_total',
      'total_points',
    ]),
    usdSpent: pickNumber(summary, [
      'usd_spent',
      'summary.usd_spent',
      'billing.usd_spent',
      'amount_spent',
    ]),
    usdBudget: pickNumber(summary, [
      'usd_budget',
      'summary.usd_budget',
      'billing.usd_budget',
      'amount_budget',
    ]),
  };
}

export default function SettingsPage() {
  const { user } = useAuthStore();
  const {
    chatBgTintLight,
    chatBgTintDark,
    tintMode,
    setChatBgTintLight,
    setChatBgTintDark,
    setTintMode,
  } = useUIStore();
  const { resolvedTheme, theme, setTheme } = useTheme();

  const [activeTab, setActiveTab] = useState('appearance');

  // General preferences
  const [writingStyle, setWritingStyle] = useState('Formal');
  const [uiLanguage, setUiLanguage] = useState<LangOption>('pt-BR');
  const [aiResponseLanguage, setAiResponseLanguage] = useState<LangOption>('pt-BR');
  const [institution, setInstitution] = useState('');
  const [role, setRole] = useState('');

  // Appearance preferences
  const [themePreference, setThemePreference] = useState<ThemePreference>('system');
  const [appearanceSaving, setAppearanceSaving] = useState(false);
  const [appearanceSaved, setAppearanceSaved] = useState(false);
  const [lightLensActive, setLightLensActive] = useState(false);
  const [darkLensActive, setDarkLensActive] = useState(false);

  // Preferences saving
  const [prefsSaving, setPrefsSaving] = useState(false);
  const [prefsSaved, setPrefsSaved] = useState(false);

  // Usage / billing data
  const [usageLoading, setUsageLoading] = useState(false);
  const [billingSummary, setBillingSummary] = useState<any>(null);
  const [billingConfig, setBillingConfig] = useState<any>(null);

  // PJe credentials state
  const [pjeCpf, setPjeCpf] = useState('');
  const [pjeSenha, setPjeSenha] = useState('');
  const [pjeSenhaSet, setPjeSenhaSet] = useState(false);
  const [showPjeSenha, setShowPjeSenha] = useState(false);
  const [pjeSaving, setPjeSaving] = useState(false);
  const [pjeSaved, setPjeSaved] = useState(false);

  useEffect(() => {
    if (theme === 'light' || theme === 'dark' || theme === 'system') {
      setThemePreference(theme);
    }
  }, [theme]);

  useEffect(() => {
    let mounted = true;

    const loadSettings = async () => {
      setUsageLoading(true);
      try {
        const [prefData, summary, billing] = await Promise.all([
          apiClient.getPreferences().catch(() => null),
          apiClient.getBillingSummary().catch(() => null),
          apiClient.getBillingConfig().catch(() => null),
        ]);

        if (!mounted) return;

        const prefs = prefData?.preferences ?? {};
        const general = prefs?.general_settings ?? {};
        const appearance = prefs?.appearance ?? {};
        const creds = prefs?.pje_credentials ?? {};

        if (general.writing_style) setWritingStyle(String(general.writing_style));
        if (general.ui_language) setUiLanguage(String(general.ui_language) as LangOption);
        if (general.ai_response_language) setAiResponseLanguage(String(general.ai_response_language) as LangOption);
        if (general.institution) setInstitution(String(general.institution));
        if (general.role) setRole(String(general.role));

        if (Number.isFinite(Number(appearance.chat_bg_tint_light))) {
          setChatBgTintLight(Number(appearance.chat_bg_tint_light));
        }
        if (Number.isFinite(Number(appearance.chat_bg_tint_dark))) {
          setChatBgTintDark(Number(appearance.chat_bg_tint_dark));
        }
        if (
          appearance.tint_mode === 'layered' ||
          appearance.tint_mode === 'blended' ||
          appearance.tint_mode === 'inset' ||
          appearance.tint_mode === 'uniform'
        ) {
          setTintMode(appearance.tint_mode);
        }
        if (
          appearance.theme_preference === 'light' ||
          appearance.theme_preference === 'dark' ||
          appearance.theme_preference === 'system'
        ) {
          setThemePreference(appearance.theme_preference);
          setTheme(appearance.theme_preference);
        }

        if (creds.cpf) setPjeCpf(String(creds.cpf));
        if (creds.senha_set) setPjeSenhaSet(true);

        setBillingSummary(summary);
        setBillingConfig(billing);
      } finally {
        if (mounted) setUsageLoading(false);
      }
    };

    loadSettings();
    return () => {
      mounted = false;
    };
  }, [setChatBgTintDark, setChatBgTintLight, setTheme, setTintMode]);

  const saveGeneralPreferences = async () => {
    setPrefsSaving(true);
    try {
      await apiClient.updatePreferences({
        general_settings: {
          writing_style: writingStyle,
          ui_language: uiLanguage,
          ai_response_language: aiResponseLanguage,
          institution,
          role,
        },
      });
      setPrefsSaved(true);
      setTimeout(() => setPrefsSaved(false), 2500);
    } finally {
      setPrefsSaving(false);
    }
  };

  const saveAppearancePreferences = async () => {
    setAppearanceSaving(true);
    try {
      await apiClient.updatePreferences({
        appearance: {
          chat_bg_tint_light: chatBgTintLight,
          chat_bg_tint_dark: chatBgTintDark,
          tint_mode: tintMode,
          theme_preference: themePreference,
        },
      });
      setTheme(themePreference);
      setAppearanceSaved(true);
      setTimeout(() => setAppearanceSaved(false), 2500);
    } finally {
      setAppearanceSaving(false);
    }
  };

  const resetAppearanceDefaults = () => {
    setChatBgTintLight(DEFAULT_CHAT_BG_TINT_LIGHT);
    setChatBgTintDark(DEFAULT_CHAT_BG_TINT_DARK);
    setTintMode(DEFAULT_TINT_MODE);
    setThemePreference('system');
  };

  const applyBlueFilterPreset = () => {
    setChatBgTintLight(PRESET_BLUE_FILTER_LIGHT_TINT);
    setChatBgTintDark(DEFAULT_CHAT_BG_TINT_DARK);
    setTintMode('layered');
  };

  const applyThemeDefaultPreset = (presetTheme: ThemePreference) => {
    setChatBgTintLight(DEFAULT_CHAT_BG_TINT_LIGHT);
    setChatBgTintDark(DEFAULT_CHAT_BG_TINT_DARK);
    setTintMode(DEFAULT_TINT_MODE);
    setThemePreference(presetTheme);
  };

  const savePjeCredentials = async () => {
    setPjeSaving(true);
    try {
      await apiClient.updatePreferences({
        pje_credentials: { cpf: pjeCpf, senha: pjeSenha || undefined },
      });
      setPjeSaved(true);
      if (pjeSenha) setPjeSenhaSet(true);
      setPjeSenha('');
      setTimeout(() => setPjeSaved(false), 3000);
    } finally {
      setPjeSaving(false);
    }
  };

  const lightGradient = useMemo(() => buildGradientTrack(LIGHT_STOPS), []);
  const darkGradient = useMemo(() => buildGradientTrack(DARK_STOPS), []);

  const lightPreview = useMemo(() => tintToColor(chatBgTintLight, LIGHT_STOPS), [chatBgTintLight]);
  const darkPreview = useMemo(() => tintToColor(chatBgTintDark, DARK_STOPS), [chatBgTintDark]);
  const lightLensPos = Math.min(96, Math.max(4, chatBgTintLight));
  const darkLensPos = Math.min(96, Math.max(4, chatBgTintDark));

  const previewIsDark = resolvedTheme === 'dark';
  const currentPreviewColor = previewIsDark ? darkPreview : lightPreview;
  const previewStyles = useMemo(
    () => getChatTintStyles({ tintMode, isDark: previewIsDark, chatBg: currentPreviewColor }),
    [currentPreviewColor, previewIsDark, tintMode],
  );

  const metrics = useMemo(() => extractMetrics(billingSummary), [billingSummary]);
  const pointsUsagePercent =
    metrics.pointsUsed != null && metrics.pointsLimit != null && metrics.pointsLimit > 0
      ? Math.min(100, Math.round((metrics.pointsUsed / metrics.pointsLimit) * 100))
      : null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Configurações</h1>
        <p className="text-muted-foreground">
          Ajustes de aparência, preferências da IA, métricas de uso e dados da conta.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="h-auto w-full flex-wrap justify-start gap-1 bg-muted/60 p-1">
          <TabsTrigger value="appearance">Aparência</TabsTrigger>
          <TabsTrigger value="preferences">Preferências</TabsTrigger>
          <TabsTrigger value="usage">Uso</TabsTrigger>
          <TabsTrigger value="billing">Faturamento</TabsTrigger>
          <TabsTrigger value="account">Cadastro</TabsTrigger>
          <TabsTrigger value="integrations">Integrações</TabsTrigger>
        </TabsList>

        <TabsContent value="appearance" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Palette className="h-5 w-5 text-indigo-600" />
                Ajustes de Aparência
              </CardTitle>
              <CardDescription>
                Configure cores e modos do chat com persistência local e no seu perfil.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-3">
                <Label>Presets rápidos</Label>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="outline" onClick={applyBlueFilterPreset}>
                    Filtro Azul (Quente)
                  </Button>
                  <Button type="button" variant="outline" onClick={() => applyThemeDefaultPreset('light')}>
                    <Sun className="mr-2 h-4 w-4" />
                    Padrão Claro
                  </Button>
                  <Button type="button" variant="outline" onClick={() => applyThemeDefaultPreset('dark')}>
                    <Moon className="mr-2 h-4 w-4" />
                    Padrão Escuro
                  </Button>
                  <Button type="button" variant="outline" onClick={() => applyThemeDefaultPreset('system')}>
                    <Monitor className="mr-2 h-4 w-4" />
                    Padrão Sistema
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  O preset Filtro Azul (Quente) aplica tons mais quentes para reduzir o azulado percebido da tela.
                </p>
              </div>

              <div className="space-y-3">
                <Label>Modo de composição visual</Label>
                <div className="grid gap-2 md:grid-cols-2">
                  {TINT_MODE_OPTIONS.map((mode) => {
                    const Icon = mode.icon;
                    const active = tintMode === mode.value;
                    return (
                      <button
                        key={mode.value}
                        type="button"
                        onClick={() => setTintMode(mode.value)}
                        className={`rounded-lg border p-3 text-left transition ${
                          active
                            ? 'border-indigo-400 bg-indigo-50/60 dark:bg-indigo-900/20'
                            : 'border-border hover:border-indigo-300'
                        }`}
                      >
                        <div className="flex items-center gap-2 text-sm font-medium">
                          <Icon className="h-4 w-4" />
                          {mode.label}
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">{mode.description}</p>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label>Tonalidade no Tema Claro</Label>
                    <span className="text-xs text-muted-foreground">{chatBgTintLight}%</span>
                  </div>
                  <div className="relative w-full rounded-full border border-border/60 shadow-sm">
                    <div
                      className={`pointer-events-none absolute -top-14 z-10 transition-opacity duration-150 ${
                        lightLensActive ? 'opacity-100' : 'opacity-0'
                      }`}
                      style={{ left: `${lightLensPos}%`, transform: 'translateX(-50%)' }}
                    >
                      <div
                        className="relative h-10 w-10 rounded-full border border-border/70 shadow-lg ring-2 ring-background/85"
                        style={{
                          background: lightGradient,
                          backgroundSize: '240% 100%',
                          backgroundPosition: `${chatBgTintLight}% 50%`,
                        }}
                      >
                        <span
                          className="absolute left-1/2 top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/80"
                          style={{ backgroundColor: lightPreview }}
                        />
                      </div>
                      <div className="mx-auto h-3 w-px bg-border/70" />
                      <div className="mt-1 rounded bg-background/95 px-1.5 py-0.5 text-[10px] text-muted-foreground shadow">
                        {lightPreview.toUpperCase()}
                      </div>
                    </div>
                    <div className="h-5 w-full rounded-full" style={{ background: lightGradient }} />
                    <input
                      type="range"
                      min={0}
                      max={100}
                      step={1}
                      value={chatBgTintLight}
                      onChange={(e) => setChatBgTintLight(Number(e.target.value))}
                      onMouseEnter={() => setLightLensActive(true)}
                      onMouseLeave={() => setLightLensActive(false)}
                      onFocus={() => setLightLensActive(true)}
                      onBlur={() => setLightLensActive(false)}
                      onPointerDown={() => setLightLensActive(true)}
                      className="chat-tint-slider absolute inset-0 h-5 w-full cursor-pointer appearance-none bg-transparent"
                      aria-label="Ajustar tonalidade no tema claro"
                    />
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>Neutro</span>
                    <span>Azulado claro</span>
                  </div>
                  <div className="h-8 rounded-md border" style={{ backgroundColor: lightPreview }} />
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label>Tonalidade no Tema Escuro</Label>
                    <span className="text-xs text-muted-foreground">{chatBgTintDark}%</span>
                  </div>
                  <div className="relative w-full rounded-full border border-border/60 shadow-sm">
                    <div
                      className={`pointer-events-none absolute -top-14 z-10 transition-opacity duration-150 ${
                        darkLensActive ? 'opacity-100' : 'opacity-0'
                      }`}
                      style={{ left: `${darkLensPos}%`, transform: 'translateX(-50%)' }}
                    >
                      <div
                        className="relative h-10 w-10 rounded-full border border-border/70 shadow-lg ring-2 ring-background/85"
                        style={{
                          background: darkGradient,
                          backgroundSize: '240% 100%',
                          backgroundPosition: `${chatBgTintDark}% 50%`,
                        }}
                      >
                        <span
                          className="absolute left-1/2 top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/80"
                          style={{ backgroundColor: darkPreview }}
                        />
                      </div>
                      <div className="mx-auto h-3 w-px bg-border/70" />
                      <div className="mt-1 rounded bg-background/95 px-1.5 py-0.5 text-[10px] text-muted-foreground shadow">
                        {darkPreview.toUpperCase()}
                      </div>
                    </div>
                    <div className="h-5 w-full rounded-full" style={{ background: darkGradient }} />
                    <input
                      type="range"
                      min={0}
                      max={100}
                      step={1}
                      value={chatBgTintDark}
                      onChange={(e) => setChatBgTintDark(Number(e.target.value))}
                      onMouseEnter={() => setDarkLensActive(true)}
                      onMouseLeave={() => setDarkLensActive(false)}
                      onFocus={() => setDarkLensActive(true)}
                      onBlur={() => setDarkLensActive(false)}
                      onPointerDown={() => setDarkLensActive(true)}
                      className="chat-tint-slider absolute inset-0 h-5 w-full cursor-pointer appearance-none bg-transparent"
                      aria-label="Ajustar tonalidade no tema escuro"
                    />
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>Escuro neutro</span>
                    <span>Frio/ardósia</span>
                  </div>
                  <div className="h-8 rounded-md border" style={{ backgroundColor: darkPreview }} />
                </div>
              </div>

              <div className="space-y-2">
                <Label>Tema padrão da aplicação</Label>
                <select
                  value={themePreference}
                  onChange={(e) => setThemePreference(e.target.value as ThemePreference)}
                  className="w-full rounded-md border bg-background p-2 text-sm"
                >
                  <option value="system">Automático (Sistema)</option>
                  <option value="light">Claro</option>
                  <option value="dark">Escuro</option>
                </select>
              </div>

              <div className="space-y-2">
                <Label>Prévia do modo atual</Label>
                <div
                  className="rounded-xl border p-3"
                  style={previewStyles.messageAreaStyle as CSSProperties}
                >
                  <div
                    className="rounded-lg border px-3 py-2 text-sm"
                    style={previewStyles.assistantBubbleStyle as CSSProperties}
                  >
                    Mensagem do assistente
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <div
                      className="rounded-md border px-2 py-2 text-xs"
                      style={previewStyles.inputAreaStyle as CSSProperties}
                    >
                      Chat Input
                    </div>
                    <div
                      className="rounded-md border px-2 py-2 text-xs"
                      style={previewStyles.canvasStyle as CSSProperties}
                    >
                      Canvas
                    </div>
                  </div>
                </div>
                <div className="text-xs text-muted-foreground">
                  Estado atual: <Badge variant="secondary" className="ml-1">{previewIsDark ? 'Tema Escuro' : 'Tema Claro'}</Badge>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" onClick={resetAppearanceDefaults}>
                  Restaurar padrão
                </Button>
                <Button type="button" onClick={saveAppearancePreferences} disabled={appearanceSaving}>
                  {appearanceSaved ? (
                    <><CheckCircle className="mr-2 h-4 w-4" />Ajustes salvos</>
                  ) : appearanceSaving ? 'Salvando...' : 'Salvar aparência'}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Os ajustes já ficam persistidos localmente no navegador. O botão de salvar também grava no perfil para sincronização.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="preferences" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Preferências Gerais</CardTitle>
              <CardDescription>
                Defina idioma da interface, idioma de resposta preferido pela IA e padrões de escrita.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="ui-language">Idioma da Interface</Label>
                  <select
                    id="ui-language"
                    value={uiLanguage}
                    onChange={(e) => setUiLanguage(e.target.value as LangOption)}
                    className="w-full rounded-md border bg-background p-2 text-sm"
                  >
                    <option value="pt-BR">Português (Brasil)</option>
                    <option value="pt-PT">Português (Portugal)</option>
                    <option value="en-US">English (US)</option>
                    <option value="es-ES">Español</option>
                  </select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="ai-language">Idioma de Resposta da IA</Label>
                  <select
                    id="ai-language"
                    value={aiResponseLanguage}
                    onChange={(e) => setAiResponseLanguage(e.target.value as LangOption)}
                    className="w-full rounded-md border bg-background p-2 text-sm"
                  >
                    <option value="pt-BR">Português (Brasil)</option>
                    <option value="pt-PT">Português (Portugal)</option>
                    <option value="en-US">English (US)</option>
                    <option value="es-ES">Español</option>
                  </select>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="writing-style">Estilo de Escrita</Label>
                  <select
                    id="writing-style"
                    value={writingStyle}
                    onChange={(e) => setWritingStyle(e.target.value)}
                    className="w-full rounded-md border bg-background p-2 text-sm"
                  >
                    <option>Formal</option>
                    <option>Técnico</option>
                    <option>Objetivo</option>
                    <option>Didático</option>
                  </select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="institution">Instituição</Label>
                  <Input
                    id="institution"
                    value={institution}
                    onChange={(e) => setInstitution(e.target.value)}
                    placeholder="Nome da instituição"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="role">Cargo/Função</Label>
                <Input
                  id="role"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  placeholder="Ex: Advogado, Juiz, Promotor"
                />
              </div>

              <Button onClick={saveGeneralPreferences} disabled={prefsSaving}>
                {prefsSaved ? (
                  <><CheckCircle className="mr-2 h-4 w-4" />Preferências salvas</>
                ) : prefsSaving ? 'Salvando...' : 'Salvar preferências'}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="usage" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Métricas de Uso</CardTitle>
              <CardDescription>
                Acompanhe pontos, orçamento e consumo agregado da sua conta.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <MetricCard label="Pontos disponíveis" value={formatNumber(metrics.pointsAvailable)} />
                <MetricCard label="Pontos usados" value={formatNumber(metrics.pointsUsed)} />
                <MetricCard label="Limite de pontos" value={formatNumber(metrics.pointsLimit)} />
                <MetricCard label="Uso" value={pointsUsagePercent == null ? '—' : `${pointsUsagePercent}%`} />
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <MetricCard label="Gasto acumulado" value={formatCurrency(metrics.usdSpent)} />
                <MetricCard label="Orçamento" value={formatCurrency(metrics.usdBudget)} />
              </div>

              <div className="text-xs text-muted-foreground">
                {usageLoading ? 'Atualizando métricas...' : 'Métricas carregadas da API de billing/usage.'}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="billing" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Faturamento</CardTitle>
              <CardDescription>
                Dados atuais de plano e configuração de custos em pontos.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 md:grid-cols-2">
                <MetricCard label="Plano" value={String(user?.plan || '—')} />
                <MetricCard label="Tipo de conta" value={String(user?.account_type || '—')} />
                <MetricCard
                  label="US$ por ponto"
                  value={
                    Number.isFinite(Number(billingConfig?.points_anchor?.usd_per_point))
                      ? `$ ${Number(billingConfig.points_anchor.usd_per_point).toFixed(6)}`
                      : '—'
                  }
                />
                <MetricCard
                  label="Moeda de referência"
                  value={String(billingConfig?.points_anchor?.currency || 'USD')}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Valores detalhados por modelo e ferramenta ficam disponíveis no seletor de modelos durante o uso do chat.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="account" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Cadastro</CardTitle>
              <CardDescription>
                Informações da conta e dados cadastrais.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2">
              <MetricCard label="Nome" value={user?.name || '—'} />
              <MetricCard label="Email" value={user?.email || '—'} />
              <MetricCard label="ID do usuário" value={user?.id || '—'} />
              <MetricCard label="Organização" value={user?.organization_id || '—'} />
              <MetricCard label="Perfil" value={user?.role || '—'} />
              <MetricCard label="Criado em" value={formatDate(user?.created_at)} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Scale className="h-5 w-5 text-blue-600" />
                Credenciais PJe
              </CardTitle>
              <CardDescription>
                Configure suas credenciais do PJe (MNI) para consulta de processos nos workflows.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="pje-cpf">CPF</Label>
                <Input
                  id="pje-cpf"
                  placeholder="000.000.000-00"
                  value={pjeCpf}
                  onChange={(e) => setPjeCpf(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="pje-senha">Senha MNI</Label>
                <div className="relative">
                  <Input
                    id="pje-senha"
                    type={showPjeSenha ? 'text' : 'password'}
                    placeholder={pjeSenhaSet ? '••••••• (já configurada)' : 'Sua senha do PJe'}
                    value={pjeSenha}
                    onChange={(e) => setPjeSenha(e.target.value)}
                  />
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                    onClick={() => setShowPjeSenha(!showPjeSenha)}
                  >
                    {showPjeSenha ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Utilizada para autenticação no Modelo Nacional de Interoperabilidade (MNI) do PJe.
                </p>
              </div>
              <Button onClick={savePjeCredentials} disabled={pjeSaving || !pjeCpf}>
                {pjeSaved ? (
                  <><CheckCircle className="mr-2 h-4 w-4" /> Salvo</>
                ) : pjeSaving ? 'Salvando...' : 'Salvar Credenciais PJe'}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="integrations" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CloudCog className="h-5 w-5 text-indigo-600" />
                Integrações DMS
              </CardTitle>
              <CardDescription>
                Conecte serviços de armazenamento externo para importar e sincronizar documentos.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <DMSIntegrations />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Servidores MCP</CardTitle>
              <CardDescription>
                Gerencie servidores MCP personalizados para expandir as ferramentas de IA.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <MCPServersConfig />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-background p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-semibold break-all">{value}</p>
    </div>
  );
}
