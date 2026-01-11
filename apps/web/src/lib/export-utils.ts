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

export const exportToHtml = (content: string, filename: string) => {
  const fullHtml = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>${filename}</title>
      <style>
        body { font-family: 'Times New Roman', serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 20px; }
        p { margin-bottom: 1em; }
      </style>
    </head>
    <body>
      ${content}
    </body>
    </html>
  `;

  const blob = new Blob([fullHtml], { type: 'text/html;charset=utf-8' });
  saveBlob(blob, `${filename}.html`);
};

export const exportToDocx = async (content: string, filename: string, auditData?: string) => {
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

  let finalContent = content;

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

export const handlePrint = (content: string) => {
  const printWindow = window.open('', '_blank');
  if (!printWindow) return;

  printWindow.document.write(`
    <html>
      <head>
        <title>Imprimir Documento</title>
        <style>
          body { font-family: 'Times New Roman', serif; line-height: 1.6; padding: 40px; }
          @media print {
            body { padding: 0; }
          }
        </style>
      </head>
      <body>
        ${content}
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
