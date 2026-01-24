'use client';

import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Database, Newspaper, Scale, Search, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { apiBaseUrl } from '@/lib/api-client';
import { formatDate } from '@/lib/utils';

type DatajudMovement = {
  nome?: string;
  data_hora?: string;
  codigo?: string;
};

type DatajudProcess = {
  numero_processo: string;
  tribunal_sigla: string;
  classe?: string;
  orgao_julgador?: string;
  sistema?: string;
  formato?: string;
  grau?: string;
  nivel_sigilo?: string;
  data_ajuizamento?: string;
  data_ultima_atualizacao?: string;
  assuntos?: string[];
  ultimo_movimento?: DatajudMovement | null;
  movimentos?: DatajudMovement[];
};

type ProcessWatchlistItem = {
  id: string;
  npu: string;
  npu_formatted?: string | null;
  tribunal_sigla: string;
  last_datajud_check?: string | null;
  last_mov_datetime?: string | null;
  is_active: boolean;
};

type OabWatchlistItem = {
  id: string;
  numero_oab: string;
  uf_oab: string;
  sigla_tribunal?: string | null;
  meio?: string | null;
  max_pages?: number | null;
  last_sync_date?: string | null;
  is_active: boolean;
};

type DjenStoredIntimation = {
  id: string;
  hash: string;
  numero_processo: string;
  numero_processo_mascara?: string | null;
  tribunal_sigla: string;
  tipo_comunicacao?: string | null;
  nome_orgao?: string | null;
  texto?: string | null;
  data_disponibilizacao?: string | null;
  meio?: string | null;
  nome_classe?: string | null;
  created_at?: string | null;
};

type DjenDestinatario = {
  nome: string;
  polo?: string | null;
};

type DjenAdvogado = {
  nome: string;
  numero_oab?: string | null;
  uf_oab?: string | null;
};

type DjenResult = {
  id: string;
  hash: string;
  numero_processo: string;
  numero_processo_mascara?: string | null;
  tribunal_sigla: string;
  tipo_comunicacao?: string | null;
  nome_orgao?: string | null;
  texto?: string | null;
  texto_resumo?: string | null;
  data_disponibilizacao?: string | null;
  meio?: string | null;
  link?: string | null;
  tipo_documento?: string | null;
  nome_classe?: string | null;
  numero_comunicacao?: number | null;
  destinatarios?: DjenDestinatario[];
  advogados?: DjenAdvogado[];
};

const toDigits = (value: string) => value.replace(/\D/g, '');

const formatNpu = (value: string) => {
  const digits = toDigits(value);
  if (digits.length !== 20) return value;
  return `${digits.slice(0, 7)}-${digits.slice(7, 9)}.${digits.slice(9, 13)}.${digits.slice(13, 14)}.${digits.slice(14, 16)}.${digits.slice(16)}`;
};

const buildJsonHeaders = (): Record<string, string> => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  if (token) {
    return {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    };
  }
  return { 'Content-Type': 'application/json' };
};

const weekdayLabels = [
  'domingo',
  'segunda-feira',
  'ter\u00e7a-feira',
  'quarta-feira',
  'quinta-feira',
  'sexta-feira',
  's\u00e1bado',
];

const htmlEntityMap: Record<string, string> = {
  '&nbsp;': ' ',
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&#39;': "'",
  '&apos;': "'",
  '&Aacute;': '\u00c1',
  '&aacute;': '\u00e1',
  '&Acirc;': '\u00c2',
  '&acirc;': '\u00e2',
  '&Atilde;': '\u00c3',
  '&atilde;': '\u00e3',
  '&Agrave;': '\u00c0',
  '&agrave;': '\u00e0',
  '&Eacute;': '\u00c9',
  '&eacute;': '\u00e9',
  '&Ecirc;': '\u00ca',
  '&ecirc;': '\u00ea',
  '&Egrave;': '\u00c8',
  '&egrave;': '\u00e8',
  '&Iacute;': '\u00cd',
  '&iacute;': '\u00ed',
  '&Icirc;': '\u00ce',
  '&icirc;': '\u00ee',
  '&Igrave;': '\u00cc',
  '&igrave;': '\u00ec',
  '&Oacute;': '\u00d3',
  '&oacute;': '\u00f3',
  '&Ocirc;': '\u00d4',
  '&ocirc;': '\u00f4',
  '&Otilde;': '\u00d5',
  '&otilde;': '\u00f5',
  '&Ograve;': '\u00d2',
  '&ograve;': '\u00f2',
  '&Uacute;': '\u00da',
  '&uacute;': '\u00fa',
  '&Ucirc;': '\u00db',
  '&ucirc;': '\u00fb',
  '&Ugrave;': '\u00d9',
  '&ugrave;': '\u00f9',
  '&Ccedil;': '\u00c7',
  '&ccedil;': '\u00e7',
  '&Ntilde;': '\u00d1',
  '&ntilde;': '\u00f1',
  '&ordm;': '\u00ba',
  '&ordf;': '\u00aa',
  '&deg;': '\u00b0',
  '&middot;': '\u00b7',
};

const decodeHtmlEntities = (value: string) => {
  const withNumeric = value
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex) => String.fromCharCode(Number.parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_, num) => String.fromCharCode(Number.parseInt(num, 10)));
  return withNumeric.replace(/&[A-Za-z]+;/g, (entity) => htmlEntityMap[entity] || entity);
};

const stripHtml = (value: string) => {
  if (!value) return '';
  const input = String(value);
  const withBreaks = input
    .replace(/<\s*br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n')
    .replace(/<\/div>/gi, '\n')
    .replace(/<\/section>/gi, '\n')
    .replace(/<\/tr>/gi, '\n')
    .replace(/<\/td>/gi, ' ')
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '');
  const withoutTags = withBreaks.replace(/<[^>]+>/g, '');
  const cleaned = decodeHtmlEntities(withoutTags)
    .replace(/\u00a0/g, ' ')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  if (cleaned) {
    return cleaned;
  }
  return decodeHtmlEntities(input).replace(/\s+/g, ' ').trim();
};

const parseDateYmd = (value?: string | null) => {
  if (!value) return null;
  const [year, month, day] = value.split('-').map((part) => Number.parseInt(part, 10));
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day);
};

const formatDateShort = (date: Date | null) => {
  if (!date) return '--';
  const day = String(date.getDate()).padStart(2, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  return `${day}/${month}`;
};

const formatDateNumeric = (value?: string | null) => {
  if (!value) return '--';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const day = String(parsed.getDate()).padStart(2, '0');
  const month = String(parsed.getMonth() + 1).padStart(2, '0');
  const year = parsed.getFullYear();
  return `${day}/${month}/${year}`;
};

const formatWeekday = (date: Date | null) => {
  if (!date) return '';
  return weekdayLabels[date.getDay()] || '';
};

const isWeekend = (date: Date) => {
  const day = date.getDay();
  return day === 0 || day === 6;
};

const addDays = (date: Date, days: number) => {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
};

const nextBusinessDay = (date: Date) => {
  let next = addDays(date, 1);
  while (isWeekend(next)) {
    next = addDays(next, 1);
  }
  return next;
};

const formatProcesso = (numero: string, mascara?: string | null) => {
  if (mascara) return mascara;
  const digits = toDigits(numero);
  if (digits.length === 20) return formatNpu(digits);
  return numero;
};

const formatMeio = (meio?: string | null) => {
  if (meio === 'E') return 'Edital';
  if (meio === 'D') return 'Diario Eletronico';
  return 'Diario Eletronico';
};

const PRAZO_URGENTE_DIAS = 5;
const PRAZO_DISTANTE_DIAS = 15;

const inferPrazoDias = (texto: string) => {
  if (!texto) return null;
  const match = texto.match(/prazo\s*(?:de\s*)?(\d{1,3})\s*dias?/i);
  if (!match) return null;
  const value = Number.parseInt(match[1], 10);
  return Number.isNaN(value) ? null : value;
};

const startOfDay = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());

const daysBetween = (from: Date, to: Date) => {
  const ms = startOfDay(to).getTime() - startOfDay(from).getTime();
  return Math.ceil(ms / (24 * 60 * 60 * 1000));
};

const getPrazoStatus = (item: DjenResult) => {
  const rawTexto = item.texto || item.texto_resumo || '';
  const teor = stripHtml(rawTexto);
  const prazoDias = inferPrazoDias(teor || rawTexto);
  if (!prazoDias) return null;
  const publicacaoDate = parseDateYmd(item.data_disponibilizacao);
  if (!publicacaoDate) return null;
  const inicioDate = nextBusinessDay(publicacaoDate);
  const vencimento = addDays(inicioDate, prazoDias);
  const diasRestantes = daysBetween(new Date(), vencimento);
  if (diasRestantes <= PRAZO_URGENTE_DIAS) {
    return 'urgente';
  }
  if (diasRestantes >= PRAZO_DISTANTE_DIAS) {
    return 'distante';
  }
  return 'normal';
};

const buildDestinatarios = (item: DjenResult) => {
  const labels: string[] = [];
  const seen = new Set<string>();
  const pushUnique = (value: string) => {
    const key = value.trim();
    if (!key || seen.has(key)) return;
    seen.add(key);
    labels.push(value);
  };

  item.destinatarios?.forEach((dest) => {
    const base = dest.nome?.trim();
    if (!base) return;
    const label = dest.polo ? `${base} (${dest.polo})` : base;
    pushUnique(label);
  });

  item.advogados?.forEach((adv) => {
    const base = adv.nome?.trim();
    if (!base) return;
    const oabParts = [adv.numero_oab, adv.uf_oab].filter(Boolean);
    const oabLabel = oabParts.length ? ` (Advogado (OAB ${oabParts.join('/')}))` : ' (Advogado)';
    pushUnique(`${base}${oabLabel}`);
  });

  return labels;
};

const buildSearchText = (item: DjenResult) => {
  const destinatarios = buildDestinatarios(item).join(' ');
  const teor = stripHtml(item.texto || item.texto_resumo || '');
  return [
    formatProcesso(item.numero_processo, item.numero_processo_mascara),
    item.numero_processo,
    item.tribunal_sigla,
    item.tipo_comunicacao,
    item.nome_orgao,
    item.nome_classe,
    teor,
    destinatarios,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
};

const escapeHtml = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const downloadFile = (content: string, filename: string, mime: string) => {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

const exportMovementsCsv = (processo: string, movements: DatajudMovement[]) => {
  if (!movements.length) {
    toast.message('Sem movimentos para exportar');
    return;
  }
  const escapeCsv = (value: string) => `"${String(value).replace(/"/g, '""')}"`;
  const rows = movements.map((mov) => [
    formatDateNumeric(mov.data_hora),
    mov.nome || 'Movimento',
  ]);
  const csv = ['Data;Movimento', ...rows.map((row) => row.map(escapeCsv).join(';'))].join('\r\n');
  const id = toDigits(processo) || 'processo';
  downloadFile(`\ufeff${csv}`, `movimentos-${id}.csv`, 'text/csv;charset=utf-8');
};

const exportMovementsPdf = (processo: string, movements: DatajudMovement[]) => {
  if (!movements.length) {
    toast.message('Sem movimentos para exportar');
    return;
  }
  const printWindow = window.open('', '_blank', 'width=900,height=700');
  if (!printWindow) {
    toast.error('Permita popups para exportar PDF');
    return;
  }
  const listItems = movements
    .map((mov) => {
      const dateLabel = formatDateNumeric(mov.data_hora);
      const name = escapeHtml(mov.nome || 'Movimento');
      return `<li><strong>${dateLabel}</strong> - ${name}</li>`;
    })
    .join('');
  const html = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Movimentos processuais</title>
    <style>
      body { font-family: Arial, sans-serif; padding: 24px; color: #111827; }
      h1 { font-size: 18px; margin-bottom: 8px; }
      p { margin: 0 0 16px; font-size: 12px; color: #4b5563; }
      ul { padding-left: 18px; }
      li { margin-bottom: 6px; font-size: 12px; }
    </style>
  </head>
  <body>
    <h1>Movimentos processuais</h1>
    <p>Processo: ${escapeHtml(processo)}</p>
    <ul>${listItems}</ul>
  </body>
</html>`;
  printWindow.document.open();
  printWindow.document.write(html);
  printWindow.document.close();
  printWindow.focus();
  printWindow.onload = () => {
    printWindow.print();
  };
};

const getMovementSortValue = (mov: DatajudMovement) => {
  if (!mov.data_hora) return null;
  const parsed = new Date(mov.data_hora);
  return Number.isNaN(parsed.getTime()) ? null : parsed.getTime();
};

const CnjMovementsSection = ({
  processo,
  movimentos,
}: {
  processo: string;
  movimentos?: DatajudMovement[];
}) => {
  const [filter, setFilter] = useState('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const filteredMovements = useMemo(() => {
    const term = filter.trim().toLowerCase();
    const base = movimentos || [];
    const filtered = term
      ? base.filter((mov) => {
          const dateLabel = formatDateNumeric(mov.data_hora).toLowerCase();
          const raw = `${mov.nome || ''} ${mov.data_hora || ''} ${dateLabel}`.toLowerCase();
          return raw.includes(term);
        })
      : base;
    return [...filtered].sort((a, b) => {
      const dateA = getMovementSortValue(a);
      const dateB = getMovementSortValue(b);
      if (dateA === null && dateB === null) return 0;
      if (dateA === null) return 1;
      if (dateB === null) return -1;
      return sortDir === 'asc' ? dateA - dateB : dateB - dateA;
    });
  }, [filter, movimentos, sortDir]);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <Input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filtrar movimentos"
          className="h-8 w-48"
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setSortDir((current) => (current === 'asc' ? 'desc' : 'asc'))}
          className="gap-1 text-xs"
        >
          Ordem
          {sortDir === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => exportMovementsCsv(processo, filteredMovements)}
        >
          Exportar CSV
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => exportMovementsPdf(processo, filteredMovements)}
        >
          Exportar PDF
        </Button>
        <span className="text-xs text-muted-foreground">{filteredMovements.length} movimentos</span>
      </div>
      <div className="mt-3 max-h-80 overflow-auto rounded-2xl border border-outline/40 bg-muted/20 p-3 text-sm text-muted-foreground">
        {filteredMovements.length ? (
          <ul className="space-y-1">
            {filteredMovements.map((mov, movIndex) => (
              <li key={`${processo}-mov-${movIndex}`}>
                {formatDateNumeric(mov.data_hora)} - {mov.nome || 'Movimento'}
              </li>
            ))}
          </ul>
        ) : (
          <span>Nenhum movimento encontrado</span>
        )}
      </div>
    </div>
  );
};

export default function CnjDjenPage() {
  const [activeTab, setActiveTab] = useState('cnj');

  const [cnjNpu, setCnjNpu] = useState('');
  const [cnjLoading, setCnjLoading] = useState(false);
  const [cnjResults, setCnjResults] = useState<DatajudProcess[]>([]);
  const [trackingTab, setTrackingTab] = useState<'processo' | 'oab'>('processo');
  const [trackProcessNpu, setTrackProcessNpu] = useState('');
  const [trackProcessTribunal, setTrackProcessTribunal] = useState('');
  const [trackOabNumero, setTrackOabNumero] = useState('');
  const [trackOabUf, setTrackOabUf] = useState('');
  const [trackOabTribunal, setTrackOabTribunal] = useState('');
  const [trackOabMeio, setTrackOabMeio] = useState<'D' | 'E'>('D');
  const [trackOabMaxPages, setTrackOabMaxPages] = useState('3');
  const [processWatchlists, setProcessWatchlists] = useState<ProcessWatchlistItem[]>([]);
  const [oabWatchlists, setOabWatchlists] = useState<OabWatchlistItem[]>([]);
  const [trackedIntimations, setTrackedIntimations] = useState<DjenStoredIntimation[]>([]);
  const [trackingLoading, setTrackingLoading] = useState(false);

  const [djenSigla, setDjenSigla] = useState('');
  const [djenOab, setDjenOab] = useState('');
  const [djenUfOab, setDjenUfOab] = useState('');
  const [djenNomeAdvogado, setDjenNomeAdvogado] = useState('');
  const [djenNomeParte, setDjenNomeParte] = useState('');
  const [djenNumeroProcesso, setDjenNumeroProcesso] = useState('');
  const [djenTexto, setDjenTexto] = useState('');
  const [djenDataInicio, setDjenDataInicio] = useState('');
  const [djenDataFim, setDjenDataFim] = useState('');
  const [djenMeio, setDjenMeio] = useState<'D' | 'E'>('D');
  const [djenItensPorPagina, setDjenItensPorPagina] = useState<'5' | '100'>('100');
  const [djenMaxPages, setDjenMaxPages] = useState('3');
  const [djenLoading, setDjenLoading] = useState(false);
  const [djenResults, setDjenResults] = useState<DjenResult[]>([]);
  const [djenIncludeTerm, setDjenIncludeTerm] = useState('');
  const [djenExcludeTerm, setDjenExcludeTerm] = useState('');
  const [djenTribunalFilter, setDjenTribunalFilter] = useState('Todos');
  const [djenSortDir, setDjenSortDir] = useState<'desc' | 'asc'>('desc');
  const [djenPrazoFilter, setDjenPrazoFilter] = useState<'all' | 'urgente' | 'distante'>('all');
  const [djenCurrentPage, setDjenCurrentPage] = useState(1);
  const [djenTotalCount, setDjenTotalCount] = useState<number | null>(null);

  const djenDisplayResults = useMemo(() => {
    const seen = new Set<string>();
    return djenResults.filter((item) => {
      const key =
        item.hash ||
        item.id ||
        [item.numero_comunicacao, item.data_disponibilizacao, item.numero_processo]
          .filter(Boolean)
          .join('|');
      if (!key) {
        return true;
      }
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [djenResults]);

  const djenTribunalOptions = useMemo(() => {
    const tribunais = new Set<string>();
    djenDisplayResults.forEach((item) => {
      if (item.tribunal_sigla) {
        tribunais.add(item.tribunal_sigla);
      }
    });
    return ['Todos', ...Array.from(tribunais).sort()];
  }, [djenDisplayResults]);

  const djenFilteredResults = useMemo(() => {
    let results = djenDisplayResults;
    const includeTerm = djenIncludeTerm.trim().toLowerCase();
    const excludeTerm = djenExcludeTerm.trim().toLowerCase();

    if (djenTribunalFilter !== 'Todos') {
      results = results.filter((item) => item.tribunal_sigla === djenTribunalFilter);
    }

    if (includeTerm) {
      results = results.filter((item) => buildSearchText(item).includes(includeTerm));
    }

    if (excludeTerm) {
      results = results.filter((item) => !buildSearchText(item).includes(excludeTerm));
    }

    if (djenPrazoFilter !== 'all') {
      results = results.filter((item) => getPrazoStatus(item) === djenPrazoFilter);
    }

    return [...results].sort((a, b) => {
      const dateA = parseDateYmd(a.data_disponibilizacao)?.getTime() ?? 0;
      const dateB = parseDateYmd(b.data_disponibilizacao)?.getTime() ?? 0;
      return djenSortDir === 'asc' ? dateA - dateB : dateB - dateA;
    });
  }, [
    djenDisplayResults,
    djenIncludeTerm,
    djenExcludeTerm,
    djenTribunalFilter,
    djenPrazoFilter,
    djenSortDir,
  ]);

  const djenItemsPerPage = Number(djenItensPorPagina);
  const djenFilteredPages = Math.max(1, Math.ceil(djenFilteredResults.length / djenItemsPerPage));
  const djenTotalPagesFromApi =
    djenTotalCount && djenItemsPerPage ? Math.ceil(djenTotalCount / djenItemsPerPage) : djenFilteredPages;
  const maxPagesLimit = Number.parseInt(djenMaxPages, 10);
  const djenPageLimit = Number.isNaN(maxPagesLimit) || maxPagesLimit < 1 ? djenTotalPagesFromApi : maxPagesLimit;
  const djenTotalPages = Math.min(djenTotalPagesFromApi, djenFilteredPages, djenPageLimit);
  const djenPageStart = (djenCurrentPage - 1) * djenItemsPerPage;
  const djenPageEnd = Math.min(djenPageStart + djenItemsPerPage, djenFilteredResults.length);
  const djenPagedResults = djenFilteredResults.slice(djenPageStart, djenPageEnd);
  const djenHasLocalFilters =
    djenIncludeTerm || djenExcludeTerm || djenTribunalFilter !== 'Todos' || djenPrazoFilter !== 'all';
  const djenTotalCountDisplay = djenHasLocalFilters
    ? djenFilteredResults.length
    : djenTotalCount ?? djenFilteredResults.length;

  const djenLimitedByMaxPages =
    !djenHasLocalFilters &&
    djenTotalCount != null &&
    djenTotalPagesFromApi > djenTotalPages &&
    djenPageLimit < djenTotalPagesFromApi;

  const hasDjenFilters = useMemo(() => {
    return Boolean(
      djenSigla ||
      djenOab ||
      djenNomeAdvogado ||
      djenNomeParte ||
      djenNumeroProcesso ||
      djenTexto
    );
  }, [djenSigla, djenOab, djenNomeAdvogado, djenNomeParte, djenNumeroProcesso, djenTexto]);

  useEffect(() => {
    setDjenCurrentPage(1);
  }, [
    djenIncludeTerm,
    djenExcludeTerm,
    djenTribunalFilter,
    djenPrazoFilter,
    djenSortDir,
    djenItensPorPagina,
    djenMaxPages,
  ]);

  useEffect(() => {
    setDjenCurrentPage((current) => Math.min(current, djenTotalPages));
  }, [djenTotalPages]);

  const handleCnjSearch = async () => {
    const npuDigits = toDigits(cnjNpu);
    if (!npuDigits) {
      toast.error('Informe o NPU do processo');
      return;
    }
    setCnjLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/djen/datajud/search`, {
        method: 'POST',
        headers: buildJsonHeaders(),
        body: JSON.stringify({
          npu: npuDigits,
        }),
      });

      const text = await response.text();
      if (!response.ok) {
        try {
          const error = JSON.parse(text);
          throw new Error(error.detail || 'Falha ao consultar DataJud');
        } catch {
          throw new Error('Resposta invalida do DataJud');
        }
      }

      let data: DatajudProcess[];
      try {
        data = JSON.parse(text) as DatajudProcess[];
      } catch {
        throw new Error('Resposta invalida do DataJud');
      }
      setCnjResults(data);
      if (!data.length) {
        toast.message('Nenhum processo encontrado');
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao consultar DataJud';
      toast.error(message);
    } finally {
      setCnjLoading(false);
    }
  };

  const handleDjenSearch = async () => {
    if (!hasDjenFilters) {
      toast.error('Informe pelo menos um filtro de busca');
      return;
    }

    if (djenOab && !djenUfOab) {
      toast.error('Informe a UF da OAB');
      return;
    }

    setDjenLoading(true);
    setDjenTotalCount(null);
    try {
      const payload: Record<string, string | number> = {};
      if (djenSigla) payload.siglaTribunal = djenSigla.trim().toUpperCase();
      if (djenOab) payload.numeroOab = toDigits(djenOab);
      if (djenUfOab) payload.ufOab = djenUfOab.trim().toUpperCase();
      if (djenNomeAdvogado) payload.nomeAdvogado = djenNomeAdvogado.trim();
      if (djenNomeParte) payload.nomeParte = djenNomeParte.trim();
      if (djenNumeroProcesso) payload.numeroProcesso = toDigits(djenNumeroProcesso);
      if (djenTexto) payload.texto = djenTexto.trim();
      if (djenDataInicio) payload.dataDisponibilizacaoInicio = djenDataInicio;
      if (djenDataFim) payload.dataDisponibilizacaoFim = djenDataFim;
      payload.meio = djenMeio;
      payload.itensPorPagina = Number(djenItensPorPagina);
      const maxPagesValue = Number.parseInt(djenMaxPages, 10);
      if (!Number.isNaN(maxPagesValue) && maxPagesValue > 0) {
        payload.maxPages = maxPagesValue;
      }

      const response = await fetch(`${apiBaseUrl}/djen/comunica/search`, {
        method: 'POST',
        headers: buildJsonHeaders(),
        body: JSON.stringify(payload),
      });

      const totalCountHeader = response.headers.get('x-total-count');
      if (totalCountHeader) {
        const parsedCount = Number.parseInt(totalCountHeader, 10);
        setDjenTotalCount(Number.isNaN(parsedCount) ? null : parsedCount);
      } else {
        setDjenTotalCount(null);
      }

      const text = await response.text();
      if (!response.ok) {
        try {
          const error = JSON.parse(text);
          throw new Error(error.detail || 'Falha ao consultar DJEN');
        } catch {
          throw new Error('Resposta invalida do DJEN. Reduza o intervalo ou limite paginas.');
        }
      }

      let data: DjenResult[];
      try {
        data = JSON.parse(text) as DjenResult[];
      } catch {
        throw new Error('Resposta invalida do DJEN. Reduza o intervalo ou limite paginas.');
      }
      setDjenResults(data);
      setDjenCurrentPage(1);
      if (!data.length) {
        toast.message('Nenhuma comunicacao encontrada');
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao consultar DJEN';
      toast.error(message);
    } finally {
      setDjenLoading(false);
    }
  };

  const djenRangeStart = djenFilteredResults.length ? djenPageStart + 1 : 0;
  const djenRangeEnd = djenFilteredResults.length ? djenPageEnd : 0;

  const trackedIntimationsSorted = useMemo(() => {
    return [...trackedIntimations].sort((a, b) => {
      const dateA = a.data_disponibilizacao ? new Date(a.data_disponibilizacao).getTime() : 0;
      const dateB = b.data_disponibilizacao ? new Date(b.data_disponibilizacao).getTime() : 0;
      return dateB - dateA;
    });
  }, [trackedIntimations]);

  const loadWatchlists = async () => {
    setTrackingLoading(true);
    try {
      const [processRes, oabRes] = await Promise.all([
        fetch(`${apiBaseUrl}/djen/watchlist`, {
          headers: buildJsonHeaders(),
        }),
        fetch(`${apiBaseUrl}/djen/watchlist/oab`, {
          headers: buildJsonHeaders(),
        }),
      ]);

      const processText = await processRes.text();
      const oabText = await oabRes.text();

      if (processRes.ok) {
        try {
          setProcessWatchlists(JSON.parse(processText) as ProcessWatchlistItem[]);
        } catch {
          setProcessWatchlists([]);
        }
      }

      if (oabRes.ok) {
        try {
          setOabWatchlists(JSON.parse(oabText) as OabWatchlistItem[]);
        } catch {
          setOabWatchlists([]);
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao carregar rastreamentos';
      toast.error(message);
    } finally {
      setTrackingLoading(false);
    }
  };

  const loadTrackedIntimations = async () => {
    setTrackingLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/djen/intimations?limit=200`, {
        headers: buildJsonHeaders(),
      });
      const text = await response.text();
      if (!response.ok) {
        throw new Error('Falha ao carregar comunicacoes monitoradas');
      }
      try {
        const data = JSON.parse(text) as DjenStoredIntimation[];
        setTrackedIntimations(data);
      } catch {
        setTrackedIntimations([]);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao carregar comunicacoes monitoradas';
      toast.error(message);
    } finally {
      setTrackingLoading(false);
    }
  };

  const handleAddProcessWatchlist = async () => {
    const npuDigits = toDigits(trackProcessNpu);
    if (!npuDigits || npuDigits.length < 10) {
      toast.error('Informe o numero do processo');
      return;
    }
    if (!trackProcessTribunal.trim()) {
      toast.error('Informe a sigla do tribunal');
      return;
    }
    setTrackingLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/djen/watchlist`, {
        method: 'POST',
        headers: buildJsonHeaders(),
        body: JSON.stringify({
          npu: npuDigits,
          tribunal_sigla: trackProcessTribunal.trim().toUpperCase(),
        }),
      });
      const text = await response.text();
      if (!response.ok) {
        try {
          const error = JSON.parse(text);
          throw new Error(error.detail || 'Falha ao adicionar processo');
        } catch {
          throw new Error('Falha ao adicionar processo');
        }
      }
      setTrackProcessNpu('');
      setTrackProcessTribunal('');
      await loadWatchlists();
      toast.message('Processo adicionado ao rastreamento diario');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao adicionar processo';
      toast.error(message);
    } finally {
      setTrackingLoading(false);
    }
  };

  const handleRemoveProcessWatchlist = async (id: string) => {
    setTrackingLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/djen/watchlist/${id}`, {
        method: 'DELETE',
        headers: buildJsonHeaders(),
      });
      if (!response.ok) {
        throw new Error('Falha ao remover processo');
      }
      await loadWatchlists();
      toast.message('Processo removido do rastreamento');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao remover processo';
      toast.error(message);
    } finally {
      setTrackingLoading(false);
    }
  };

  const handleAddOabWatchlist = async () => {
    const oabDigits = toDigits(trackOabNumero);
    if (!oabDigits) {
      toast.error('Informe o numero da OAB');
      return;
    }
    if (!trackOabUf.trim()) {
      toast.error('Informe a UF da OAB');
      return;
    }
    const maxPagesValue = Number.parseInt(trackOabMaxPages, 10);
    setTrackingLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/djen/watchlist/oab`, {
        method: 'POST',
        headers: buildJsonHeaders(),
        body: JSON.stringify({
          numero_oab: oabDigits,
          uf_oab: trackOabUf.trim().toUpperCase(),
          sigla_tribunal: trackOabTribunal.trim().toUpperCase() || null,
          meio: trackOabMeio,
          max_pages: Number.isNaN(maxPagesValue) ? 3 : maxPagesValue,
        }),
      });
      const text = await response.text();
      if (!response.ok) {
        try {
          const error = JSON.parse(text);
          throw new Error(error.detail || 'Falha ao adicionar OAB');
        } catch {
          throw new Error('Falha ao adicionar OAB');
        }
      }
      setTrackOabNumero('');
      setTrackOabUf('');
      setTrackOabTribunal('');
      await loadWatchlists();
      toast.message('OAB adicionada ao rastreamento diario');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao adicionar OAB';
      toast.error(message);
    } finally {
      setTrackingLoading(false);
    }
  };

  const handleRemoveOabWatchlist = async (id: string) => {
    setTrackingLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/djen/watchlist/oab/${id}`, {
        method: 'DELETE',
        headers: buildJsonHeaders(),
      });
      if (!response.ok) {
        throw new Error('Falha ao remover OAB');
      }
      await loadWatchlists();
      toast.message('OAB removida do rastreamento');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao remover OAB';
      toast.error(message);
    } finally {
      setTrackingLoading(false);
    }
  };

  const handleSyncProcessWatchlist = async () => {
    setTrackingLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/djen/sync?include_process=true&include_oab=false`, {
        method: 'POST',
        headers: buildJsonHeaders(),
      });
      const text = await response.text();
      if (!response.ok) {
        throw new Error('Falha ao sincronizar processos');
      }
      const payload = JSON.parse(text) as { new_intimations?: number };
      toast.message(`Sincronizacao concluida: ${payload.new_intimations ?? 0} novas comunicacoes`);
      await loadWatchlists();
      await loadTrackedIntimations();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao sincronizar processos';
      toast.error(message);
    } finally {
      setTrackingLoading(false);
    }
  };

  const handleSyncOabWatchlist = async () => {
    setTrackingLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/djen/sync?include_process=false&include_oab=true`, {
        method: 'POST',
        headers: buildJsonHeaders(),
      });
      const text = await response.text();
      if (!response.ok) {
        throw new Error('Falha ao sincronizar OAB');
      }
      const payload = JSON.parse(text) as { new_intimations?: number };
      toast.message(`Sincronizacao concluida: ${payload.new_intimations ?? 0} novas comunicacoes`);
      await loadWatchlists();
      await loadTrackedIntimations();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao sincronizar OAB';
      toast.error(message);
    } finally {
      setTrackingLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'tracking') {
      void loadWatchlists();
      void loadTrackedIntimations();
    }
  }, [activeTab]);

  return (
    <div className="space-y-8">
      <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
        <p className="text-xs font-semibold uppercase text-muted-foreground">Ferramenta CNJ + DJEN</p>
        <h1 className="font-display text-3xl text-foreground">Metadados CNJ e Comunicacoes DJEN</h1>
        <p className="text-sm text-muted-foreground">
          Consulte metadados processuais (DataJud) e publicacoes oficiais (DJEN) em um unico painel.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-white/90 shadow-soft">
          <TabsTrigger value="cnj" className="gap-2">
            <Database className="h-4 w-4" />
            Metadados CNJ
          </TabsTrigger>
          <TabsTrigger value="tracking" className="gap-2">
            <Newspaper className="h-4 w-4" />
            Rastreamento diario
          </TabsTrigger>
          <TabsTrigger value="djen" className="gap-2">
            <Newspaper className="h-4 w-4" />
            Comunicacoes DJEN
          </TabsTrigger>
        </TabsList>

        <TabsContent value="cnj" className="space-y-6">
          <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
            <div className="flex items-center gap-3 text-sm font-semibold text-foreground">
              <Scale className="h-4 w-4 text-primary" />
              Metadados Judiciais CNJ
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Consulte os metadados de um processo na base de dados publica do CNJ (DataJud).
            </p>

            <div className="mt-5 space-y-2">
              <Label htmlFor="cnj-npu">Numero do Processo</Label>
              <Input
                id="cnj-npu"
                placeholder="0000000-00.0000.0.00.0000"
                value={cnjNpu}
                onChange={(event) => setCnjNpu(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Digite o numero completo do processo com a formatacao CNJ.
              </p>
            </div>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Button onClick={handleCnjSearch} disabled={cnjLoading}>
                <Search className="mr-2 h-4 w-4" />
                {cnjLoading ? 'Consultando...' : 'Consultar'}
              </Button>
              <Button
                variant="outline"
                onClick={() => setCnjResults([])}
                disabled={cnjLoading || cnjResults.length === 0}
              >
                Limpar resultados
              </Button>
            </div>
          </div>

          <div className="space-y-3">
            {cnjResults.map((item, index) => (
              <div
                key={`${item.numero_processo}-${index}`}
                className="rounded-3xl border border-outline/40 bg-white p-5 shadow-soft"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-foreground">{formatNpu(item.numero_processo)}</p>
                    <p className="text-xs text-muted-foreground">{item.tribunal_sigla}</p>
                  </div>
                  {item.ultimo_movimento?.data_hora && (
                    <span className="rounded-full bg-primary/10 px-3 py-1 text-xs text-primary">
                      {formatDate(item.ultimo_movimento.data_hora)}
                    </span>
                  )}
                </div>

                <div className="mt-4 space-y-3">
                  <div>
                    <p className="text-xs font-semibold uppercase text-muted-foreground">Identificacao do processo</p>
                    <div className="mt-2 grid gap-2 text-sm text-muted-foreground md:grid-cols-2">
                      <p>
                        <span className="font-semibold text-foreground">Numero:</span>{' '}
                        {formatNpu(item.numero_processo)}
                      </p>
                      <p>
                        <span className="font-semibold text-foreground">Tribunal:</span>{' '}
                        {item.tribunal_sigla || 'Nao informado'}
                      </p>
                      <p>
                        <span className="font-semibold text-foreground">Classe:</span>{' '}
                        {item.classe || 'Nao informado'}
                      </p>
                      <p>
                        <span className="font-semibold text-foreground">Sistema:</span>{' '}
                        {item.sistema || 'Nao informado'}
                      </p>
                      <p>
                        <span className="font-semibold text-foreground">Formato:</span>{' '}
                        {item.formato || 'Nao informado'}
                      </p>
                      <p>
                        <span className="font-semibold text-foreground">Grau:</span>{' '}
                        {item.grau || 'Nao informado'}
                      </p>
                      <p>
                        <span className="font-semibold text-foreground">Nivel de sigilo:</span>{' '}
                        {item.nivel_sigilo || 'Nao informado'}
                      </p>
                      <p>
                        <span className="font-semibold text-foreground">Orgao julgador:</span>{' '}
                        {item.orgao_julgador || 'Nao informado'}
                      </p>
                      {item.data_ajuizamento && (
                        <p>
                          <span className="font-semibold text-foreground">Data ajuizamento:</span>{' '}
                          {formatDate(item.data_ajuizamento)}
                        </p>
                      )}
                      {item.data_ultima_atualizacao && (
                        <p>
                          <span className="font-semibold text-foreground">Ultima atualizacao:</span>{' '}
                          {formatDate(item.data_ultima_atualizacao)}
                        </p>
                      )}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold uppercase text-muted-foreground">Assuntos do processo</p>
                    <div className="mt-2 text-sm text-muted-foreground">
                      {item.assuntos && item.assuntos.length ? (
                        <ul className="list-disc space-y-1 pl-4">
                          {item.assuntos.map((assunto, assuntoIndex) => (
                            <li key={`${item.numero_processo}-assunto-${assuntoIndex}`}>{assunto}</li>
                          ))}
                        </ul>
                      ) : (
                        <span>Nao informado</span>
                      )}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold uppercase text-muted-foreground">Movimentos processuais</p>
                    <div className="mt-2">
                      <CnjMovementsSection
                        processo={formatNpu(item.numero_processo)}
                        movimentos={item.movimentos || []}
                      />
                    </div>
                  </div>
                </div>
              </div>
            ))}
            {!cnjLoading && cnjResults.length === 0 && (
              <div className="rounded-3xl border border-dashed border-outline/50 bg-white/70 p-6 text-sm text-muted-foreground">
                Nenhum resultado ainda. Execute uma consulta para ver os metadados do CNJ.
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="tracking" className="space-y-6">
          <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
            <div className="flex items-center gap-3 text-sm font-semibold text-foreground">
              <Newspaper className="h-4 w-4 text-primary" />
              Rastreamento diario
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Ative o monitoramento diario por processo ou OAB. O sistema busca movimentacoes e comunicacoes no horario
              programado.
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button variant="outline" onClick={loadWatchlists} disabled={trackingLoading}>
                Atualizar listas
              </Button>
              <Button variant="outline" onClick={loadTrackedIntimations} disabled={trackingLoading}>
                Atualizar comunicacoes
              </Button>
            </div>

            <Tabs value={trackingTab} onValueChange={(value) => setTrackingTab(value as 'processo' | 'oab')} className="mt-5">
              <TabsList className="bg-white/90 shadow-soft">
                <TabsTrigger value="processo">Por processo</TabsTrigger>
                <TabsTrigger value="oab">Por OAB</TabsTrigger>
              </TabsList>

              <TabsContent value="processo" className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-3">
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="track-processo-npu">Numero do processo</Label>
                    <Input
                      id="track-processo-npu"
                      placeholder="12345671220248130000"
                      value={trackProcessNpu}
                      onChange={(event) => setTrackProcessNpu(event.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="track-processo-tribunal">Tribunal</Label>
                    <Input
                      id="track-processo-tribunal"
                      placeholder="TJMG"
                      value={trackProcessTribunal}
                      onChange={(event) => setTrackProcessTribunal(event.target.value)}
                    />
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <Button onClick={handleAddProcessWatchlist} disabled={trackingLoading}>
                    Adicionar rastreamento
                  </Button>
                  <Button variant="outline" onClick={handleSyncProcessWatchlist} disabled={trackingLoading}>
                    Sincronizar agora
                  </Button>
                </div>

                <div className="space-y-2">
                  {processWatchlists.length === 0 && (
                    <div className="rounded-2xl border border-dashed border-outline/50 bg-white/70 p-4 text-sm text-muted-foreground">
                      Nenhum processo monitorado ainda.
                    </div>
                  )}
                  {processWatchlists.map((item) => (
                    <div key={item.id} className="rounded-2xl border border-outline/40 bg-white px-4 py-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <p className="text-sm font-semibold text-foreground">
                            {formatNpu(item.npu_formatted || item.npu)}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {item.tribunal_sigla} • Ultimo movimento{' '}
                            {item.last_mov_datetime ? formatDate(item.last_mov_datetime) : 'Nao identificado'}
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoveProcessWatchlist(item.id)}
                          disabled={trackingLoading}
                        >
                          Desativar
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </TabsContent>

              <TabsContent value="oab" className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-3">
                  <div className="space-y-2">
                    <Label htmlFor="track-oab-numero">Numero OAB</Label>
                    <Input
                      id="track-oab-numero"
                      placeholder="150334"
                      value={trackOabNumero}
                      onChange={(event) => setTrackOabNumero(event.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="track-oab-uf">UF</Label>
                    <Input
                      id="track-oab-uf"
                      placeholder="MG"
                      value={trackOabUf}
                      onChange={(event) => setTrackOabUf(event.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="track-oab-tribunal">Tribunal (opcional)</Label>
                    <Input
                      id="track-oab-tribunal"
                      placeholder="TJMG"
                      value={trackOabTribunal}
                      onChange={(event) => setTrackOabTribunal(event.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="track-oab-meio">Meio</Label>
                    <Select value={trackOabMeio} onValueChange={(value) => setTrackOabMeio(value as 'D' | 'E')}>
                      <SelectTrigger id="track-oab-meio">
                        <SelectValue placeholder="Selecione" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="D">Diario</SelectItem>
                        <SelectItem value="E">Edital</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="track-oab-max-pages">Max paginas</Label>
                    <Input
                      id="track-oab-max-pages"
                      inputMode="numeric"
                      placeholder="3"
                      value={trackOabMaxPages}
                      onChange={(event) => setTrackOabMaxPages(event.target.value)}
                    />
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <Button onClick={handleAddOabWatchlist} disabled={trackingLoading}>
                    Adicionar rastreamento
                  </Button>
                  <Button variant="outline" onClick={handleSyncOabWatchlist} disabled={trackingLoading}>
                    Sincronizar agora
                  </Button>
                </div>

                <div className="space-y-2">
                  {oabWatchlists.length === 0 && (
                    <div className="rounded-2xl border border-dashed border-outline/50 bg-white/70 p-4 text-sm text-muted-foreground">
                      Nenhuma OAB monitorada ainda.
                    </div>
                  )}
                  {oabWatchlists.map((item) => (
                    <div key={item.id} className="rounded-2xl border border-outline/40 bg-white px-4 py-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <p className="text-sm font-semibold text-foreground">
                            {item.numero_oab}/{item.uf_oab}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {item.sigla_tribunal || 'Todos os tribunais'} • Ultima sincronizacao{' '}
                            {item.last_sync_date ? formatDate(item.last_sync_date) : 'Nao realizada'}
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoveOabWatchlist(item.id)}
                          disabled={trackingLoading}
                        >
                          Desativar
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </TabsContent>
            </Tabs>
          </div>

          <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
            <div className="flex items-center gap-3 text-sm font-semibold text-foreground">
              <Newspaper className="h-4 w-4 text-primary" />
              Comunicacoes monitoradas
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Lista de comunicacoes capturadas pelo rastreamento diario.
            </p>
            <div className="mt-4 space-y-3">
              {trackedIntimationsSorted.map((item) => {
                const publicacaoDate = parseDateYmd(item.data_disponibilizacao);
                const inicioDate = publicacaoDate ? nextBusinessDay(publicacaoDate) : null;
                const teor = stripHtml(item.texto || '');
                const prazoDias = inferPrazoDias(teor);
                const prazoLabel = prazoDias ? `${prazoDias} dias` : 'Nao identificado';
                return (
                  <div key={item.id} className="rounded-3xl border border-outline/40 bg-white p-5 shadow-soft">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="space-y-1">
                        <p className="text-sm font-semibold text-foreground">
                          Processo: {formatProcesso(item.numero_processo, item.numero_processo_mascara)}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {item.tipo_comunicacao || 'Intimacao'} {'\u2022'} {item.tribunal_sigla || 'DJEN'}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-outline/40 bg-muted/30 px-4 py-3 text-xs">
                        <div className="min-w-[90px] space-y-1">
                          <p className="text-[10px] font-semibold uppercase text-muted-foreground">Publicacao</p>
                          <p className="text-sm font-semibold text-foreground">{formatDateShort(publicacaoDate)}</p>
                          <p className="text-[11px] text-muted-foreground">
                            {formatWeekday(publicacaoDate)}
                            {publicacaoDate && isWeekend(publicacaoDate) && (
                              <span className="ml-1 text-[10px] uppercase text-amber-600">(nao util)</span>
                            )}
                          </p>
                        </div>
                        <span className="text-muted-foreground">{'\u2192'}</span>
                        <div className="min-w-[90px] space-y-1">
                          <p className="text-[10px] font-semibold uppercase text-muted-foreground">Inicio</p>
                          <p className="text-sm font-semibold text-foreground">{formatDateShort(inicioDate)}</p>
                          <p className="text-[11px] text-muted-foreground">{formatWeekday(inicioDate)}</p>
                        </div>
                        <span className="text-muted-foreground">{'\u2192'}</span>
                        <div className="rounded-xl border border-outline/50 bg-white/70 px-3 py-2">
                          <p className="text-[10px] font-semibold uppercase text-muted-foreground">Prazo</p>
                          <p className="text-xs font-semibold text-foreground">{prazoLabel}</p>
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 space-y-1">
                      {item.nome_orgao && (
                        <p className="text-xs font-semibold uppercase text-muted-foreground">{item.nome_orgao}</p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        <span className="font-semibold text-foreground">Meio:</span> {formatMeio(item.meio)}
                      </p>
                      {item.nome_classe && (
                        <p className="text-xs text-muted-foreground">
                          <span className="font-semibold text-foreground">Classe:</span> {item.nome_classe}
                        </p>
                      )}
                    </div>

                    <div className="mt-4">
                      <p className="text-xs font-semibold uppercase text-muted-foreground">Teor:</p>
                      <p className="mt-2 whitespace-pre-line text-sm text-muted-foreground">
                        {teor || 'Sem teor disponivel.'}
                      </p>
                    </div>
                  </div>
                );
              })}
              {!trackingLoading && trackedIntimationsSorted.length === 0 && (
                <div className="rounded-3xl border border-dashed border-outline/50 bg-white/70 p-6 text-sm text-muted-foreground">
                  Nenhuma comunicacao monitorada ainda. Execute uma sincronizacao para carregar resultados.
                </div>
              )}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="djen" className="space-y-6">
          <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
            <div className="flex items-center gap-3 text-sm font-semibold text-foreground">
              <Newspaper className="h-4 w-4 text-primary" />
              Consulta DJEN (Comunica)
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Preencha ao menos um filtro. Consultas amplas podem ser limitadas pela API.
            </p>

            <div className="mt-5 grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="djen-tribunal">Tribunal</Label>
                <Input
                  id="djen-tribunal"
                  placeholder="TJMG"
                  value={djenSigla}
                  onChange={(event) => setDjenSigla(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="djen-oab">Numero OAB</Label>
                <Input
                  id="djen-oab"
                  placeholder="12345"
                  value={djenOab}
                  onChange={(event) => setDjenOab(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="djen-uf-oab">UF OAB</Label>
                <Input
                  id="djen-uf-oab"
                  placeholder="MG"
                  value={djenUfOab}
                  onChange={(event) => setDjenUfOab(event.target.value)}
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="djen-advogado">Nome do advogado</Label>
                <Input
                  id="djen-advogado"
                  placeholder="Nome completo ou parcial"
                  value={djenNomeAdvogado}
                  onChange={(event) => setDjenNomeAdvogado(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="djen-meio">Meio</Label>
                <Select value={djenMeio} onValueChange={(value) => setDjenMeio(value as 'D' | 'E')}>
                  <SelectTrigger id="djen-meio">
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="D">Diario</SelectItem>
                    <SelectItem value="E">Edital</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="djen-parte">Nome da parte</Label>
                <Input
                  id="djen-parte"
                  placeholder="Parte autora ou re"
                  value={djenNomeParte}
                  onChange={(event) => setDjenNomeParte(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="djen-processo">Numero do processo</Label>
                <Input
                  id="djen-processo"
                  placeholder="12345671220248130000"
                  value={djenNumeroProcesso}
                  onChange={(event) => setDjenNumeroProcesso(event.target.value)}
                />
              </div>
              <div className="space-y-2 md:col-span-3">
                <Label htmlFor="djen-texto">Texto livre</Label>
                <Input
                  id="djen-texto"
                  placeholder="Termo especifico, palavra-chave ou trecho"
                  value={djenTexto}
                  onChange={(event) => setDjenTexto(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="djen-data-inicio">Data inicio</Label>
                <Input
                  id="djen-data-inicio"
                  type="date"
                  value={djenDataInicio}
                  onChange={(event) => setDjenDataInicio(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="djen-data-fim">Data fim</Label>
                <Input
                  id="djen-data-fim"
                  type="date"
                  value={djenDataFim}
                  onChange={(event) => setDjenDataFim(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="djen-itens">Itens por pagina</Label>
                <Select value={djenItensPorPagina} onValueChange={(value) => setDjenItensPorPagina(value as '5' | '100')}>
                  <SelectTrigger id="djen-itens">
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="5">5</SelectItem>
                    <SelectItem value="100">100</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="djen-max-pages">Max paginas (API)</Label>
                <Input
                  id="djen-max-pages"
                  inputMode="numeric"
                  placeholder="3"
                  value={djenMaxPages}
                  onChange={(event) => setDjenMaxPages(event.target.value)}
                />
              </div>
            </div>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Button onClick={handleDjenSearch} disabled={djenLoading}>
                <Search className="mr-2 h-4 w-4" />
                {djenLoading ? 'Consultando...' : 'Buscar comunicacoes'}
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setDjenResults([]);
                  setDjenTotalCount(null);
                }}
                disabled={djenLoading || djenResults.length === 0}
              >
                Limpar resultados
              </Button>
            </div>
          </div>

          <div className="rounded-3xl border border-outline/40 bg-white/95 p-4 shadow-soft">
            <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
              <span className="font-semibold text-foreground">
                Resultados: {djenRangeStart}-{djenRangeEnd} de {djenTotalCountDisplay} comunicacoes
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={djenCurrentPage <= 1}
                  onClick={() => setDjenCurrentPage((current) => Math.max(1, current - 1))}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-xs text-muted-foreground">
                  {djenCurrentPage}/{djenTotalPages}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={djenCurrentPage >= djenTotalPages}
                  onClick={() => setDjenCurrentPage((current) => Math.min(djenTotalPages, current + 1))}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => toast.message('Analise com IA em breve')}
                className="gap-2"
              >
                <Sparkles className="h-3.5 w-3.5" />
                Analisar com IA
              </Button>
              {djenLimitedByMaxPages && (
                <span className="text-xs text-amber-600">
                  Limitado a {djenPageLimit} paginas
                </span>
              )}
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2">
                <Label htmlFor="djen-incluir" className="text-xs text-muted-foreground">
                  Incluir
                </Label>
                <Input
                  id="djen-incluir"
                  placeholder="termo"
                  value={djenIncludeTerm}
                  onChange={(event) => setDjenIncludeTerm(event.target.value)}
                  className="h-8 w-40"
                />
              </div>
              <div className="flex items-center gap-2">
                <Label htmlFor="djen-excluir" className="text-xs text-muted-foreground">
                  Excluir
                </Label>
                <Input
                  id="djen-excluir"
                  placeholder="termo"
                  value={djenExcludeTerm}
                  onChange={(event) => setDjenExcludeTerm(event.target.value)}
                  className="h-8 w-40"
                />
              </div>
              <div className="flex items-center gap-2">
                <Label className="text-xs text-muted-foreground">Tribunal</Label>
                <Select value={djenTribunalFilter} onValueChange={setDjenTribunalFilter}>
                  <SelectTrigger className="h-8 w-36">
                    <SelectValue placeholder="Todos" />
                  </SelectTrigger>
                  <SelectContent>
                    {djenTribunalOptions.map((tribunal) => (
                      <SelectItem key={tribunal} value={tribunal}>
                        {tribunal}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-2">
                <Label className="text-xs text-muted-foreground">Ordenar</Label>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setDjenSortDir((current) => (current === 'desc' ? 'asc' : 'desc'))}
                  className="gap-1 text-xs"
                >
                  Data
                  {djenSortDir === 'desc' ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />}
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <Label className="text-xs text-muted-foreground">Prazo</Label>
                <Select value={djenPrazoFilter} onValueChange={(value) => setDjenPrazoFilter(value as 'all' | 'urgente' | 'distante')}>
                  <SelectTrigger className="h-8 w-32">
                    <SelectValue placeholder="Todos" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="urgente">Urgente</SelectItem>
                    <SelectItem value="distante">Distante</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            {djenPagedResults.map((item) => {
              const publicacaoDate = parseDateYmd(item.data_disponibilizacao);
              const inicioDate = publicacaoDate ? nextBusinessDay(publicacaoDate) : null;
              const destinatarios = buildDestinatarios(item);
              const rawTexto = item.texto || item.texto_resumo || '';
              const teor = stripHtml(rawTexto);
              const prazoDias = inferPrazoDias(teor || rawTexto);
              const prazoLabel = prazoDias ? `${prazoDias} dias` : 'Nao identificado';
              const fallbackKey =
                item.hash ||
                item.id ||
                [item.numero_comunicacao, item.data_disponibilizacao, item.numero_processo]
                  .filter(Boolean)
                  .join('|');
              return (
                <div
                  key={fallbackKey || item.id}
                  className="rounded-3xl border border-outline/40 bg-white p-5 shadow-soft"
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-foreground">
                        Processo: {formatProcesso(item.numero_processo, item.numero_processo_mascara)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {item.tipo_comunicacao || 'Intimacao'} {'\u2022'} {item.tribunal_sigla || 'DJEN'}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-outline/40 bg-muted/30 px-4 py-3 text-xs">
                      <div className="min-w-[90px] space-y-1">
                        <p className="text-[10px] font-semibold uppercase text-muted-foreground">Publicacao</p>
                        <p className="text-sm font-semibold text-foreground">{formatDateShort(publicacaoDate)}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {formatWeekday(publicacaoDate)}
                          {publicacaoDate && isWeekend(publicacaoDate) && (
                            <span className="ml-1 text-[10px] uppercase text-amber-600">(nao util)</span>
                          )}
                        </p>
                      </div>
                      <span className="text-muted-foreground">{'\u2192'}</span>
                      <div className="min-w-[90px] space-y-1">
                        <p className="text-[10px] font-semibold uppercase text-muted-foreground">Inicio</p>
                        <p className="text-sm font-semibold text-foreground">{formatDateShort(inicioDate)}</p>
                        <p className="text-[11px] text-muted-foreground">{formatWeekday(inicioDate)}</p>
                      </div>
                      <span className="text-muted-foreground">{'\u2192'}</span>
                      <div className="rounded-xl border border-outline/50 bg-white/70 px-3 py-2">
                        <p className="text-[10px] font-semibold uppercase text-muted-foreground">Prazo</p>
                        <p className="text-xs font-semibold text-foreground">{prazoLabel}</p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 space-y-1">
                    {item.nome_orgao && (
                      <p className="text-xs font-semibold uppercase text-muted-foreground">{item.nome_orgao}</p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      <span className="font-semibold text-foreground">Meio:</span> {formatMeio(item.meio)}
                    </p>
                    {item.nome_classe && (
                      <p className="text-xs text-muted-foreground">
                        <span className="font-semibold text-foreground">Classe:</span> {item.nome_classe}
                      </p>
                    )}
                  </div>

                  {destinatarios.length > 0 && (
                    <div className="mt-4">
                      <p className="text-xs font-semibold uppercase text-muted-foreground">Destinatarios:</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {destinatarios.map((label, index) => (
                          <span
                            key={`${item.id}-dest-${index}`}
                            className="rounded-full border border-outline/40 bg-muted/30 px-3 py-1 text-xs text-foreground"
                          >
                            {label}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="mt-4">
                    <p className="text-xs font-semibold uppercase text-muted-foreground">Teor:</p>
                    <p className="mt-2 whitespace-pre-line text-sm text-muted-foreground">
                      {teor || 'Sem teor disponivel.'}
                    </p>
                  </div>
                </div>
              );
            })}
            {!djenLoading && djenFilteredResults.length === 0 && (
              <div className="rounded-3xl border border-dashed border-outline/50 bg-white/70 p-6 text-sm text-muted-foreground">
                Nenhuma comunicacao exibida. Use os filtros acima para consultar o DJEN.
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
