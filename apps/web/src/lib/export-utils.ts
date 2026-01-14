// Utilitários de exportação sem dependências externas

const saveBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

export const exportToTxt = (content: string, filename: string) => {
  // Remover tags HTML simples para obter texto puro
  const tempDiv = document.createElement('div');
  tempDiv.innerHTML = content;
  const text = tempDiv.textContent || tempDiv.innerText || '';

  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  saveBlob(blob, `${filename}.txt`);
};

let mermaidConfigured = false;

const getSvgDimensions = (svg: string) => {
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(svg, 'image/svg+xml');
    const svgEl = doc.documentElement;
    const widthAttr = svgEl.getAttribute('width');
    const heightAttr = svgEl.getAttribute('height');
    const viewBox = svgEl.getAttribute('viewBox');

    const parseSize = (value: string | null) => {
      if (!value) return null;
      const num = parseFloat(value.replace('px', '').trim());
      return Number.isFinite(num) && num > 0 ? num : null;
    };

    const width = parseSize(widthAttr);
    const height = parseSize(heightAttr);
    if (width && height) return { width, height };

    if (viewBox) {
      const parts = viewBox.split(/\s+/).map((v) => Number(v));
      if (parts.length === 4 && parts.every((v) => Number.isFinite(v))) {
        const vbWidth = Math.max(1, parts[2]);
        const vbHeight = Math.max(1, parts[3]);
        return { width: vbWidth, height: vbHeight };
      }
    }
  } catch {
    // Fallback below.
  }

  return { width: 800, height: 450 };
};

const svgToPngDataUrl = (svg: string) =>
  new Promise<string>((resolve, reject) => {
    const { width, height } = getSvgDimensions(svg);
    const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          throw new Error('Canvas context unavailable');
        }
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, width, height);
        ctx.drawImage(img, 0, 0, width, height);
        URL.revokeObjectURL(url);
        resolve(canvas.toDataURL('image/png'));
      } catch (err) {
        URL.revokeObjectURL(url);
        reject(err);
      }
    };
    img.onerror = (err) => {
      URL.revokeObjectURL(url);
      reject(err);
    };
    img.src = url;
  });

const replaceMermaidBlocks = async (content: string, mode: 'html' | 'docx' | 'print') => {
  if (typeof window === 'undefined') return content;
  if (!content || !content.includes('language-mermaid')) return content;

  const container = document.createElement('div');
  container.innerHTML = content;
  const blocks = Array.from(
    container.querySelectorAll('pre > code[class*="language-mermaid"]')
  );

  if (!blocks.length) return content;

  const mermaidModule = await import('mermaid');
  const mermaid = mermaidModule.default;
  if (!mermaidConfigured) {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'default',
      securityLevel: 'loose',
      fontFamily: 'inherit',
    });
    mermaidConfigured = true;
  }

  for (const codeEl of blocks) {
    const pre = codeEl.parentElement;
    if (!pre) continue;
    const diagramCode = (codeEl.textContent || '').trim();
    if (!diagramCode) continue;

    try {
      const id = `export-mermaid-${Math.random().toString(36).slice(2)}`;
      const { svg } = await mermaid.render(id, diagramCode);

      if (mode === 'docx') {
        const dataUrl = await svgToPngDataUrl(svg);
        const img = document.createElement('img');
        img.src = dataUrl;
        img.alt = 'Diagrama Mermaid';
        img.style.maxWidth = '100%';
        img.style.display = 'block';
        img.style.margin = '12px 0';
        pre.replaceWith(img);
      } else {
        const figure = document.createElement('figure');
        figure.setAttribute('data-diagram', 'mermaid');
        figure.style.margin = '12px 0';
        figure.innerHTML = svg;
        const svgEl = figure.querySelector('svg');
        if (svgEl) {
          svgEl.setAttribute('style', 'max-width:100%;height:auto;');
        }
        pre.replaceWith(figure);
      }
    } catch {
      // If rendering fails, keep the original code block.
    }
  }

  return container.innerHTML;
};

export const exportToHtml = async (content: string, filename: string) => {
  const safeContent = await replaceMermaidBlocks(content, 'html');
  const fullHtml = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>${filename}</title>
      <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Google+Sans+Text:wght@400;500;600;700&display=swap">
      <style>
        body { font-family: "Google Sans Text", "Google Sans", -apple-system, "Segoe UI", sans-serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 20px; font-size: 12px; color: #000; background: #fff; }
        .editor-output p { margin-bottom: 0.5rem; }
        .editor-output p:last-child { margin-bottom: 0; }
        .editor-output ul { margin-bottom: 0.5rem; padding-left: 1.25rem; list-style: disc; }
        .editor-output ol { margin-bottom: 0.5rem; padding-left: 1.25rem; list-style: decimal; }
        .editor-output li { margin-bottom: 0.25rem; }
        .editor-output blockquote { margin-bottom: 0.75rem; border-left: 2px solid #cbd5e1; padding-left: 0.75rem; color: #334155; }
        .editor-output pre { margin: 0.75rem 0; overflow: auto; border-radius: 6px; background: #f1f5f9; padding: 12px; font-size: 11px; line-height: 1.5; }
        .editor-output code { border-radius: 4px; background: #f1f5f9; padding: 2px 4px; font-size: 11px; }
        .editor-output pre code { background: transparent; padding: 0; }
        .editor-output table { margin: 0.75rem 0; width: 100%; border-collapse: collapse; font-size: 12px; }
        .editor-output th, .editor-output td { border: 1px solid #e2e8f0; padding: 6px 8px; vertical-align: top; }
        .editor-output th { background: #f1f5f9; font-weight: 600; }
        .editor-output table tr:nth-child(even) td { background: #f8fafc; }
        .editor-output img { max-width: 100%; border-radius: 8px; border: 1px solid #e2e8f0; }
        .editor-output h1 { margin-bottom: 0.5rem; font-size: 16px; font-weight: 600; }
        .editor-output h2 { margin-bottom: 0.5rem; font-size: 14px; font-weight: 600; }
        .editor-output h3 { margin-bottom: 0.5rem; font-size: 13px; font-weight: 600; }
        .editor-output h4, .editor-output h5, .editor-output h6 { margin-bottom: 0.5rem; font-size: 12px; font-weight: 600; }
        .editor-output a { color: #2563eb; text-decoration: underline; text-underline-offset: 2px; }
        figure[data-diagram="mermaid"] { margin: 12px 0; }
      </style>
    </head>
    <body>
      <div class="editor-output">${safeContent}</div>
    </body>
    </html>
  `;

  const blob = new Blob([fullHtml], { type: 'text/html;charset=utf-8' });
  saveBlob(blob, `${filename}.html`);
};

export const exportToDocx = async (content: string, filename: string, auditData?: string) => {
  const safeContent = await replaceMermaidBlocks(content, 'docx');
  // Fallback robusto: HTML compatível com Word
  const preHtml = `
    <html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
    <head>
      <meta charset='utf-8'>
      <title>${filename}</title>
      <style>
        body { font-family: 'Times New Roman', serif; font-size: 12pt; }
        p { margin-bottom: 1em; }
        .audit-section { margin-top: 40px; border-top: 2px solid #ccc; padding-top: 20px; }
        .audit-title { color: #d97706; font-size: 14pt; font-weight: bold; margin-bottom: 10px; }
        .audit-content { font-family: 'Courier New', monospace; font-size: 10pt; background-color: #fffbeb; padding: 15px; }
      </style>
    </head>
    <body>
  `;

  let finalContent = safeContent;

  // Append Audit Report if present
  if (auditData) {
    // Basic markdown to html conversion for audit part if needed, or wrap in pre
    // For simplicity in Word, we'll wrap in a styled div
    finalContent += `
        <div class="audit-section">
            <div class="audit-title">⚠️ RELATÓRIO DE AUDITORIA IA</div>
            <div class="audit-content">
                ${auditData.replace(/\n/g, '<br/>')}
            </div>
        </div>
      `;
  }

  const postHtml = "</body></html>";
  const html = preHtml + finalContent + postHtml;

  const blob = new Blob(['\ufeff', html], {
    type: 'application/msword'
  });

  saveBlob(blob, `${filename}.doc`);
};

export const handlePrint = async (content: string) => {
  const printWindow = window.open('', '_blank');
  if (!printWindow) return;
  const safeContent = await replaceMermaidBlocks(content, 'print');

  printWindow.document.write(`
    <html>
      <head>
        <title>Imprimir Documento</title>
        <style>
          body { font-family: 'Times New Roman', serif; line-height: 1.6; padding: 40px; }
          figure[data-diagram="mermaid"] { margin: 12px 0; }
          @media print {
            body { padding: 0; }
          }
        </style>
      </head>
      <body>
        ${safeContent}
      </body>
    </html>
  `);

  printWindow.document.close();
  printWindow.focus();

  // Aguarda carregar estilos/imagens antes de imprimir
  setTimeout(() => {
    printWindow.print();
    printWindow.close();
  }, 250);
};
