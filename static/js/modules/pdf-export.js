/**
 * PDF Export Module
 * PDF导出模块
 */

class PDFExporter {
  constructor() {
    this.isExporting = false;
  }

  formatDateTime(value) {
    if (!window.Utils || typeof window.Utils.formatDateTime !== 'function') {
      return '';
    }

    return window.Utils.formatDateTime(value);
  }

  sanitizeFilenamePart(value, fallback = 'file') {
    const text = typeof value === 'string' ? value.trim() : '';
    if (!text) {
      return fallback;
    }

    return text
      .replace(/[\/\\]/g, '-')
      .replace(/[?%*:|"<>]/g, '-')
      .replace(/\./g, '-')
      .replace(/\s+/g, '_')
      .replace(/,/g, '')
      .replace(/-+/g, '-')
      .replace(/_+/g, '_')
      .replace(/^[-_]+|[-_]+$/g, '');
  }

  formatFilenameDate(value) {
    const formatted = this.formatDateTime(value);
    if (!formatted) {
      return new Date().toISOString().slice(0, 10);
    }

    return this.sanitizeFilenamePart(formatted, new Date().toISOString().slice(0, 10));
  }

  async exportToPDF() {
    if (this.isExporting) return;

    const btn = document.getElementById('export-pdf-btn');
    if (!btn) return;

    const oldText = btn.innerHTML;
    btn.innerHTML = '⏳ 生成中...';
    btn.disabled = true;
    this.isExporting = true;

    try {
      const node = this.buildPDFNode();
      if (document.fonts && document.fonts.ready) {
        try { await document.fonts.ready; } catch (_) { }
      }
      await new Promise(r => setTimeout(r, 40));

      const { jsPDF } = window.jspdf || {};
      if (!jsPDF) throw new Error('jsPDF 加载失败');

      const canvas = await html2canvas(node, {
        scale: window.devicePixelRatio > 2 ? 2 : 2,
        useCORS: true,
        backgroundColor: '#ffffff'
      });

      // Create a master white-backed canvas and draw the html2canvas result onto it.
      // This guarantees the canvas has an opaque white background and removes any
      // remaining alpha/transparency that could turn black during encoding.
      const master = document.createElement('canvas');
      master.width = canvas.width;
      master.height = canvas.height;
      const mctx = master.getContext('2d');
      mctx.fillStyle = '#ffffff';
      mctx.fillRect(0, 0, master.width, master.height);
      mctx.drawImage(canvas, 0, 0);

  // TODO[TechDebt]: 已用白底 master canvas 作为临时修复，若后续仍有问题需实现更鲁棒的分块策略。

      const pdf = new jsPDF('p', 'mm', 'a4');
      const pageW = 210, pageH = 297, margin = 10, availH = pageH - 2 * margin;
  const imgW = pageW - 2 * margin;
  const imgH = master.height * imgW / master.width;

      if (imgH <= availH) {
        // Use PNG from the master (white-backed) canvas to ensure opaque background
        pdf.addImage(master.toDataURL('image/png'), 'PNG', margin, margin, imgW, imgH);
      } else {
        const slicePxH = availH * master.width / imgW;
        const temp = document.createElement('canvas');
        temp.width = canvas.width;
        let tempHeight = slicePxH;
        temp.height = tempHeight;
        let ctx = temp.getContext('2d');

        let y = 0;
        let page = 0;
        while (y < canvas.height) {
          // compute current slice height (last slice may be smaller)
          const curH = Math.min(slicePxH, canvas.height - y);
          if (temp.height !== curH) {
            temp.height = curH;
            ctx = temp.getContext('2d');
          }
          // fill white background to avoid transparency turning black when saving as JPEG
          ctx.fillStyle = '#ffffff';
          ctx.fillRect(0, 0, temp.width, temp.height);
          // Draw from the master canvas (white-backed) to avoid any alpha issues
          ctx.drawImage(master, 0, y, master.width, curH, 0, 0, master.width, curH);
          const dataUrl = temp.toDataURL('image/png');
          // compute scaled height in mm for this slice
          const scaledH = curH * imgW / master.width;
          if (page > 0) pdf.addPage();
          pdf.addImage(dataUrl, 'PNG', margin, margin, imgW, scaledH);
          y += curH;
          page++;
        }
      }

      const title = this.sanitizeFilenamePart(document.getElementById('lesson-title')?.textContent || '日语课文练习', '日语课文练习');
      const filename = `${title}_${this.formatFilenameDate(new Date().toISOString())}.pdf`;
      pdf.save(filename);

    } catch (err) {
      console.error('PDF导出失败', err);
      if (window.Toast) {
        window.Toast.error('PDF导出失败: ' + err.message);
      } else {
        alert('PDF导出失败: ' + err.message);
      }
    } finally {
      btn.innerHTML = oldText;
      btn.disabled = false;
      this.isExporting = false;
      const tmp = document.getElementById('__pdf_tmp_wrapper');
      if (tmp) tmp.remove();
    }
  }

  buildPDFNode() {
    const wrap = document.createElement('div');
    wrap.id = '__pdf_tmp_wrapper';
    wrap.style.cssText = 'position:fixed;left:-9999px;top:0;width:800px;background:#fff;padding:24px;font-family:\'Noto Sans JP\',Arial,sans-serif;line-height:1.6;';

    const title = (document.getElementById('lesson-title')?.textContent || '日语课文练习');
    const ruby = document.getElementById('highlight-text')?.innerHTML || '';
    const translation = document.querySelector('.translation-text')?.innerHTML || '';
    const vocabItems = Array.from(document.querySelectorAll('.vocab-item'));

    const vocabHTML = vocabItems.map(it => `<div style="border:1px solid #f8bbd9;background:#fce4ec;padding:6px 8px;border-radius:6px;">
        <div style='font-size:11px;color:#880e4f;'>${it.querySelector('.vocab-pronunciation')?.textContent || ''}</div>
        <div style='font-size:13px;font-weight:600;color:#880e4f;'>${it.querySelector('.vocab-word')?.textContent || ''}</div>
        <div style='font-size:11px;color:#ad1457;'>${it.querySelector('.vocab-meaning')?.textContent || ''}</div>
    </div>`).join('');

    wrap.innerHTML = `
        <h1 style='text-align:center;color:#ad1457;margin:0 0 8px;font-size:24px;'>📚 ${title}</h1>
        <p style='text-align:center;margin:0 0 18px;color:#666;font-size:12px;'>生成时间: ${this.formatDateTime(new Date().toISOString())}</p>
        ${ruby ? `<section style='margin-bottom:18px;padding:12px 16px;background:#fff3e0;border-left:4px solid #ff9800;border-radius:6px;'><h2 style='margin:0 0 8px;font-size:16px;color:#ff9800;'>🔤 注音文本</h2><div style='font-size:15px;line-height:2;'>${ruby}</div></section>` : ''}
        ${translation ? `<section style='margin-bottom:18px;padding:12px 16px;background:#e8f5e8;border-left:4px solid #4caf50;border-radius:6px;'><h2 style='margin:0 0 8px;font-size:16px;color:#4caf50;'>🇨🇳 中文翻译</h2><div style='font-size:15px;'>${translation}</div></section>` : ''}
        ${vocabItems.length ? `<section style='margin-bottom:18px;padding:12px 16px;background:#fce4ec;border-left:4px solid #e91e63;border-radius:6px;'><h2 style='margin:0 0 8px;font-size:16px;color:#e91e63;'>📖 词汇表</h2><div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;'>${vocabHTML}</div></section>` : ''}
        <footer style='text-align:center;margin-top:24px;padding-top:12px;border-top:1px solid #ddd;font-size:11px;color:#666;'>🌟 YomuTomo 自动生成 · 继续加油！</footer>`;

    document.body.appendChild(wrap);
    return wrap;
  }
}

// Export for global use
window.PDFExporter = PDFExporter;
