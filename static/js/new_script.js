// Form validation and modal management
document.addEventListener('DOMContentLoaded', function () {
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', function (e) {
            const config = getStoredConfig();
            if (!config.apiKey) {
                alert('请先配置AI设置');
                e.preventDefault();
                openConfigModal();
                return;
            }

            // Add config to form data
            const apiKeyInput = document.createElement('input');
            apiKeyInput.type = 'hidden';
            apiKeyInput.name = 'api_key';
            apiKeyInput.value = config.apiKey;

            const baseUrlInput = document.createElement('input');
            baseUrlInput.type = 'hidden';
            baseUrlInput.name = 'base_url';
            baseUrlInput.value = config.baseUrl || '';

            const modelInput = document.createElement('input');
            modelInput.type = 'hidden';
            modelInput.name = 'model';
            modelInput.value = config.model || 'gpt-5-mini';

            form.appendChild(apiKeyInput);
            form.appendChild(baseUrlInput);
            form.appendChild(modelInput);

            // Show loading state
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.innerHTML = '⏳ 处理中...';
                submitBtn.disabled = true;
            }
        });
    }

    // Initialize config status
    updateConfigStatus();

    // Modal event listeners
    setupModalEvents();

    // Floating label support (ensure labels float when value present even if :placeholder-shown not reliable)
    function refreshFloating() {
        document.querySelectorAll('.input-group').forEach(group => {
            const field = group.querySelector('input, textarea, select');
            const label = group.querySelector('label');
            if (!field || !label) return;
            if (field.value && field.value.trim() !== '') {
                label.classList.add('force-float');
            } else {
                label.classList.remove('force-float');
            }
        });
    }
    document.addEventListener('input', e => {
        if (e.target.matches('.input-group input, .input-group textarea, .input-group select')) {
            refreshFloating();
        }
    });
    refreshFloating();
});

function setupModalEvents() {
    const configBtn = document.getElementById('config-btn');
    const closeBtn = document.getElementById('close-modal');
    const cancelBtn = document.getElementById('cancel-config');
    const saveBtn = document.getElementById('save-config');
    const modal = document.getElementById('config-modal');

    if (configBtn) {
        configBtn.addEventListener('click', openConfigModal);
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', closeConfigModal);
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', closeConfigModal);
    }

    if (saveBtn) {
        saveBtn.addEventListener('click', saveConfig);
    }

    // Close modal when clicking outside
    if (modal) {
        modal.addEventListener('click', function (e) {
            if (e.target === modal) {
                closeConfigModal();
            }
        });
    }

    // Close modal on Escape key
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal && modal.classList.contains('show')) {
            closeConfigModal();
        }
    });
}

function openConfigModal() {
    const modal = document.getElementById('config-modal');
    const config = getStoredConfig();

    // Populate modal with stored values
    const apiKeyInput = document.getElementById('modal-api-key');
    const baseUrlInput = document.getElementById('modal-base-url');
    const modelSelect = document.getElementById('modal-model');

    if (apiKeyInput) apiKeyInput.value = config.apiKey || '';
    if (baseUrlInput) baseUrlInput.value = config.baseUrl || 'https://api.openai.com/v1';
    if (modelSelect) modelSelect.value = config.model || 'gpt-5-mini';

    if (modal) {
        modal.classList.add('show');
        document.body.style.overflow = 'hidden';
    }
}

function closeConfigModal() {
    const modal = document.getElementById('config-modal');
    if (modal) {
        modal.classList.remove('show');
        document.body.style.overflow = 'auto';
    }
}

function saveConfig() {
    const apiKey = document.getElementById('modal-api-key').value.trim();
    const baseUrl = document.getElementById('modal-base-url').value.trim();
    const model = document.getElementById('modal-model').value;

    if (!apiKey) {
        alert('请输入API Key');
        return;
    }

    // Save to localStorage
    const config = {
        apiKey: apiKey,
        baseUrl: baseUrl,
        model: model,
        timestamp: Date.now()
    };

    localStorage.setItem('aiConfig', JSON.stringify(config));

    // Update status
    updateConfigStatus();

    // Show success feedback
    showSaveSuccess();

    // Close modal
    setTimeout(() => {
        closeConfigModal();
    }, 1500);
}

function getStoredConfig() {
    const stored = localStorage.getItem('aiConfig');
    return stored ? JSON.parse(stored) : {};
}

function updateConfigStatus() {
    const config = getStoredConfig();
    const statusDiv = document.getElementById('config-status');
    const statusIcon = document.getElementById('status-icon');
    const statusText = document.getElementById('status-text');

    if (statusDiv && statusIcon && statusText) {
        if (config.apiKey) {
            statusDiv.classList.add('configured');
            statusIcon.textContent = '✅';
            statusText.textContent = `已配置 (${config.model})`;
        } else {
            statusDiv.classList.remove('configured');
            statusIcon.textContent = '❌';
            statusText.textContent = '未配置';
        }
    }
}

function showSaveSuccess() {
    const saveBtn = document.getElementById('save-config');
    if (saveBtn) {
        const originalText = saveBtn.innerHTML;
        saveBtn.innerHTML = '✅ 保存成功！';
        saveBtn.classList.add('success-animation');
        saveBtn.disabled = true;

        setTimeout(() => {
            saveBtn.innerHTML = originalText;
            saveBtn.classList.remove('success-animation');
            saveBtn.disabled = false;
        }, 1500);
    }
}

// Speech Recognition
let recognition;
let finalTranscript = '';

if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'ja-JP';
} else {
    console.warn('浏览器不支持语音识别');
}

function initSpeechRecognition() {
    if (!recognition) return;

    const recordBtn = document.getElementById('record-btn');
    const stopBtn = document.getElementById('stop-btn');
    const resultDiv = document.getElementById('result');

    if (recordBtn) {
        recordBtn.addEventListener('click', () => {
            finalTranscript = '';
            recognition.start();
            recordBtn.disabled = true;
            recordBtn.innerHTML = '🎤 录音中...';
            if (stopBtn) stopBtn.disabled = false;
            if (resultDiv) resultDiv.innerHTML = '<p style="color: var(--success-color);">正在录音，请开始朗读...</p>';

            // 激活荧光特效
            const readingContainer = document.querySelector('.main-content');
            if (readingContainer) {
                readingContainer.classList.add('recording-active');
            }

            const highlightText = document.getElementById('highlight-text');
            if (highlightText) {
                // 从隐藏元素获取原文数据
                const originalTextElement = document.getElementById('original-text');
                const rubyTextElement = document.getElementById('ruby-text-data');
                const originalText = originalTextElement ? originalTextElement.textContent : '';
                const rubyText = rubyTextElement ? rubyTextElement.innerHTML : '';

                // 初始状态：所有词都是待读状态
                const words = originalText.split(/\s+/);
                let initialHTML = rubyText;

                // 将所有词标记为待读状态
                words.forEach(word => {
                    if (word.trim()) {
                        const regex = new RegExp(`(${word})`, 'g');
                        initialHTML = initialHTML.replace(regex, `<span class="karaoke-pending">$1</span>`);
                    }
                });

                highlightText.innerHTML = initialHTML;
            }
        });
    }

    if (stopBtn) {
        stopBtn.addEventListener('click', () => {
            recognition.stop();
            recordBtn.disabled = false;
            recordBtn.innerHTML = '▶️ 开始录音';
            stopBtn.disabled = true;
            if (resultDiv) resultDiv.innerHTML = '<p style="color: var(--warning-color);">录音已停止，正在处理...</p>';

            // 移除荧光特效
            const readingContainer = document.querySelector('.main-content');
            if (readingContainer) {
                readingContainer.classList.remove('recording-active');
            }
        });
    }

    recognition.onresult = (event) => {
        let interimTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
            let transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += transcript;
            } else {
                interimTranscript += transcript;
            }
        }

        if (resultDiv) {
            resultDiv.innerHTML = `
                <p><strong>识别文本：</strong>${finalTranscript}<span style="color: var(--text-secondary); font-style: italic;">${interimTranscript}</span></p>
            `;
        }

        // Highlight matching text
        if (finalTranscript) {
            highlightText(finalTranscript);
        }
    };

    recognition.onerror = (event) => {
        console.error('语音识别错误:', event.error);
        if (resultDiv) {
            resultDiv.innerHTML = `<p style="color: var(--danger-color);">语音识别错误: ${event.error}</p>`;
        }
        resetButtons();
    };

    recognition.onend = () => {
        resetButtons();
        if (finalTranscript) {
            // Send to backend for evaluation
            evaluateSpeech(finalTranscript);
        }
    };
}

function resetButtons() {
    const recordBtn = document.getElementById('record-btn');
    const stopBtn = document.getElementById('stop-btn');

    if (recordBtn) {
        recordBtn.disabled = false;
        recordBtn.innerHTML = '▶️ 开始录音';
    }
    if (stopBtn) {
        stopBtn.disabled = true;
    }

    // 移除荧光特效
    const readingContainer = document.querySelector('.main-content');
    if (readingContainer) {
        readingContainer.classList.remove('recording-active');
    }
}

function highlightText(recognized) {
    const highlightText = document.getElementById('highlight-text');
    if (!highlightText) return;

    // 从隐藏元素获取原文数据
    const originalTextElement = document.getElementById('original-text');
    const rubyTextElement = document.getElementById('ruby-text-data');
    const originalText = originalTextElement ? originalTextElement.textContent : '';
    const rubyText = rubyTextElement ? rubyTextElement.innerHTML : '';

    // 如果没有识别到内容，显示原始的带注音文本
    if (!recognized || recognized.trim() === '') {
        highlightText.innerHTML = rubyText;
        return;
    }

    // 卡拉OK式高亮：根据识别进度逐渐点亮文本
    const recognizedWords = recognized.trim().split(/\s+/);
    const originalWords = originalText.split(/\s+/);

    let highlightedHTML = '';
    let recognizedIndex = 0;
    let originalIndex = 0;

    // 解析ruby文本，提取纯文本词语
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = rubyText;
    const textContent = tempDiv.textContent || tempDiv.innerText || '';

    // 重新构建带高亮的HTML
    let rubyHTML = rubyText;
    let currentPos = 0;

    while (originalIndex < originalWords.length && recognizedIndex < recognizedWords.length) {
        const originalWord = originalWords[originalIndex];
        const recognizedWord = recognizedWords[recognizedIndex];

        // 检查是否匹配
        if (checkWordMatch(originalWord, recognizedWord)) {
            // 找到匹配的词，在rubyHTML中替换为高亮版本
            const wordIndex = rubyHTML.indexOf(originalWord, currentPos);
            if (wordIndex !== -1) {
                const beforeWord = rubyHTML.substring(0, wordIndex);
                const afterWord = rubyHTML.substring(wordIndex + originalWord.length);
                rubyHTML = beforeWord + `<span class="karaoke-highlight">${originalWord}</span>` + afterWord;
                currentPos = wordIndex + originalWord.length + `<span class="karaoke-highlight">${originalWord}</span>`.length;
            }

            recognizedIndex++;
        } else {
            // 尝试向前查找匹配
            let found = false;
            for (let i = 0; i < 3 && originalIndex + i < originalWords.length; i++) {
                if (checkWordMatch(originalWords[originalIndex + i], recognizedWord)) {
                    // 标记跳过的词为待读状态
                    for (let j = 0; j < i; j++) {
                        const skipWord = originalWords[originalIndex + j];
                        const skipIndex = rubyHTML.indexOf(skipWord, currentPos);
                        if (skipIndex !== -1) {
                            const beforeSkip = rubyHTML.substring(0, skipIndex);
                            const afterSkip = rubyHTML.substring(skipIndex + skipWord.length);
                            rubyHTML = beforeSkip + `<span class="karaoke-pending">${skipWord}</span>` + afterSkip;
                        }
                    }

                    // 高亮匹配的词
                    const matchWord = originalWords[originalIndex + i];
                    const matchIndex = rubyHTML.indexOf(matchWord, currentPos);
                    if (matchIndex !== -1) {
                        const beforeMatch = rubyHTML.substring(0, matchIndex);
                        const afterMatch = rubyHTML.substring(matchIndex + matchWord.length);
                        rubyHTML = beforeMatch + `<span class="karaoke-highlight">${matchWord}</span>` + afterMatch;
                        currentPos = matchIndex + matchWord.length + `<span class="karaoke-highlight">${matchWord}</span>`.length;
                    }

                    originalIndex += i;
                    recognizedIndex++;
                    found = true;
                    break;
                }
            }

            if (!found) {
                // 没有找到匹配，标记为待读
                const pendingWord = originalWord;
                const pendingIndex = rubyHTML.indexOf(pendingWord, currentPos);
                if (pendingIndex !== -1) {
                    const beforePending = rubyHTML.substring(0, pendingIndex);
                    const afterPending = rubyHTML.substring(pendingIndex + pendingWord.length);
                    rubyHTML = beforePending + `<span class="karaoke-pending">${pendingWord}</span>` + afterPending;
                }
            }
        }

        originalIndex++;
    }

    // 处理剩余的词
    while (originalIndex < originalWords.length) {
        const remainingWord = originalWords[originalIndex];
        const remainingIndex = rubyHTML.indexOf(remainingWord, currentPos);
        if (remainingIndex !== -1) {
            const beforeRemaining = rubyHTML.substring(0, remainingIndex);
            const afterRemaining = rubyHTML.substring(remainingIndex + remainingWord.length);
            rubyHTML = beforeRemaining + `<span class="karaoke-pending">${remainingWord}</span>` + afterRemaining;
        }
        originalIndex++;
    }

    highlightText.innerHTML = rubyHTML;
}

function checkWordMatch(originalWord, recognizedWord) {
    // 移除标点符号进行比较
    const cleanOriginal = originalWord.replace(/[。、，！？「」『』()（）【】《》〈〉]/g, '');
    const cleanRecognized = recognizedWord.replace(/[。、，！？「」『』()（）【】《》〈〉]/g, '');

    // 完全匹配
    if (cleanOriginal === cleanRecognized) {
        return true;
    }

    // 长度相似且包含相同字符
    if (Math.abs(cleanOriginal.length - cleanRecognized.length) <= 1) {
        const similarity = calculateSimilarity(cleanOriginal, cleanRecognized);
        return similarity > 0.8;
    }

    return false;
}

function calculateSimilarity(str1, str2) {
    const longer = str1.length > str2.length ? str1 : str2;
    const shorter = str1.length > str2.length ? str2 : str1;

    if (longer.length === 0) return 1.0;

    const distance = levenshteinDistance(longer, shorter);
    return (longer.length - distance) / longer.length;
}

function levenshteinDistance(str1, str2) {
    const matrix = [];

    for (let i = 0; i <= str2.length; i++) {
        matrix[i] = [i];
    }

    for (let j = 0; j <= str1.length; j++) {
        matrix[0][j] = j;
    }

    for (let i = 1; i <= str2.length; i++) {
        for (let j = 1; j <= str1.length; j++) {
            if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
                matrix[i][j] = matrix[i - 1][j - 1];
            } else {
                matrix[i][j] = Math.min(
                    matrix[i - 1][j - 1] + 1,
                    matrix[i][j - 1] + 1,
                    matrix[i - 1][j] + 1
                );
            }
        }
    }

    return matrix[str2.length][str1.length];
}

function evaluateSpeech(recognizedText) {
    const resultDiv = document.getElementById('result');
    const config = getStoredConfig();

    // 从隐藏元素获取原文数据
    const originalTextElement = document.getElementById('original-text');
    const originalText = originalTextElement ? originalTextElement.textContent : '';

    fetch('/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
            original: originalText,
            recognized: recognizedText
        })
    })
        .then(response => response.json())
        .then(data => {
            if (resultDiv) {
                const scoreColor = data.score >= 80 ? 'var(--success-color)' : data.score >= 60 ? 'var(--warning-color)' : 'var(--danger-color)';
                resultDiv.innerHTML += `<p><strong>评分：</strong><span style="color: ${scoreColor}; font-size: 1.2em;">${data.score}/100</span></p>`;
            }
        })
        .catch(error => {
            console.error('评测错误:', error);
            if (resultDiv) {
                resultDiv.innerHTML += `<p style="color: var(--danger-color);">评测失败，请重试</p>`;
            }
        });
}

function removeWord(btn) {
    const item = btn.closest('.vocab-item');
    if (item) {
        item.style.animation = 'fadeOut 0.3s ease-out';
        setTimeout(() => {
            item.remove();
        }, 300);
    }
}

// Add fadeOut animation
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeOut {
        to {
            opacity: 0;
            transform: translateX(100%);
        }
    }
`;
document.head.appendChild(style);

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    initSpeechRecognition();
    // 绑定 PDF 导出
    const exportBtn = document.getElementById('export-pdf-btn');
    if (exportBtn) exportBtn.addEventListener('click', exportToPDF);
    // 缓存内容（延迟避免尚未渲染完全）
    setTimeout(cacheContent, 800);
    // 清除任何遗留的 beforeunload
    window.onbeforeunload = null;
});

// ===== 内容缓存（避免刷新后重新调用AI） =====
function cacheContent(){
    try {
        const data = {
            original: document.getElementById('original-text')?.textContent || '',
            ruby: document.getElementById('highlight-text')?.innerHTML || '',
            translation: document.querySelector('.translation-text')?.innerHTML || '',
            title: document.getElementById('lesson-title')?.textContent || '',
            vocab: Array.from(document.querySelectorAll('.vocab-item')).map(v=>({
                word: v.querySelector('.vocab-word')?.textContent || '',
                pronunciation: v.querySelector('.vocab-pronunciation')?.textContent || '',
                meaning: v.querySelector('.vocab-meaning')?.textContent || ''
            })),
            ts: Date.now()
        };
        if (data.original) localStorage.setItem('lessonContent', JSON.stringify(data));
    } catch(e){console.warn('缓存失败', e);} }

// ===== jsPDF 导出 =====
async function exportToPDF(){
    const btn = document.getElementById('export-pdf-btn');
    if (!btn) return;
    const old = btn.innerHTML; btn.innerHTML='⏳ 生成中...'; btn.disabled=true;
    try {
        const node = buildPDFNode();
        if (document.fonts && document.fonts.ready) { try { await document.fonts.ready; } catch(_){} }
        await new Promise(r=>setTimeout(r,40));
        const { jsPDF } = window.jspdf || {};
        if (!jsPDF) throw new Error('jsPDF 加载失败');
        const canvas = await html2canvas(node,{scale: window.devicePixelRatio>2?2:2, useCORS:true, backgroundColor:'#ffffff'});
        const pdf = new jsPDF('p','mm','a4');
        const pageW=210, pageH=297, margin=10, availH=pageH-2*margin;
        const imgW = pageW-2*margin;
        const imgH = canvas.height * imgW / canvas.width;
        if (imgH <= availH){
            pdf.addImage(canvas.toDataURL('image/jpeg',0.95),'JPEG',margin,margin,imgW,imgH);
        } else {
            const slicePxH = availH * canvas.width / imgW;
            const temp = document.createElement('canvas');
            temp.width = canvas.width; temp.height = slicePxH; const ctx = temp.getContext('2d');
            let y=0; let page=0;
            while (y < canvas.height){
                ctx.clearRect(0,0,temp.width,temp.height);
                ctx.drawImage(canvas,0,y,canvas.width,slicePxH,0,0,canvas.width,slicePxH);
                const dataUrl = temp.toDataURL('image/jpeg',0.95);
                if (page>0) pdf.addPage();
                pdf.addImage(dataUrl,'JPEG',margin,margin,imgW,availH);
                y += slicePxH; page++;
            }
        }
        const title = (document.getElementById('lesson-title')?.textContent || '日语课文练习').trim();
        const filename = `${title}_${new Date().toLocaleDateString('zh-CN').replace(/\//g,'-')}.pdf`;
        pdf.save(filename);
    } catch(err){
        console.error('PDF导出失败',err);
        alert('PDF导出失败: '+err.message);
    } finally {
        btn.innerHTML=old; btn.disabled=false;
        const tmp=document.getElementById('__pdf_tmp_wrapper'); if (tmp) tmp.remove();
    }
}

function buildPDFNode(){
    const wrap = document.createElement('div');
    wrap.id='__pdf_tmp_wrapper';
    wrap.style.cssText='position:fixed;left:-9999px;top:0;width:800px;background:#fff;padding:24px;font-family:\'Noto Sans JP\',Arial,sans-serif;line-height:1.6;';
    const title = (document.getElementById('lesson-title')?.textContent||'日语课文练习');
    // 不再需要原文，只导出注音/翻译/词汇
    const original = ''; // 保留变量，兼容后续逻辑
    const ruby = document.getElementById('highlight-text')?.innerHTML || '';
    const translation = document.querySelector('.translation-text')?.innerHTML || '';
    const vocabItems = Array.from(document.querySelectorAll('.vocab-item'));
    const vocabHTML = vocabItems.map(it=>`<div style="border:1px solid #f8bbd9;background:#fce4ec;padding:6px 8px;border-radius:6px;">
        <div style='font-size:11px;color:#880e4f;'>${it.querySelector('.vocab-pronunciation')?.textContent||''}</div>
        <div style='font-size:13px;font-weight:600;color:#880e4f;'>${it.querySelector('.vocab-word')?.textContent||''}</div>
        <div style='font-size:11px;color:#ad1457;'>${it.querySelector('.vocab-meaning')?.textContent||''}</div>
    </div>`).join('');
    wrap.innerHTML = `
        <h1 style='text-align:center;color:#ad1457;margin:0 0 8px;font-size:24px;'>📚 ${title}</h1>
        <p style='text-align:center;margin:0 0 18px;color:#666;font-size:12px;'>生成时间: ${new Date().toLocaleString('zh-CN')}</p>
    <!-- 原文已按需求省略 -->
        ${ruby?`<section style='margin-bottom:18px;padding:12px 16px;background:#fff3e0;border-left:4px solid #ff9800;border-radius:6px;'><h2 style='margin:0 0 8px;font-size:16px;color:#ff9800;'>🔤 注音文本</h2><div style='font-size:15px;line-height:2;'>${ruby}</div></section>`:''}
        ${translation?`<section style='margin-bottom:18px;padding:12px 16px;background:#e8f5e8;border-left:4px solid #4caf50;border-radius:6px;'><h2 style='margin:0 0 8px;font-size:16px;color:#4caf50;'>🇨🇳 中文翻译</h2><div style='font-size:15px;'>${translation}</div></section>`:''}
        ${vocabItems.length?`<section style='margin-bottom:18px;padding:12px 16px;background:#fce4ec;border-left:4px solid #e91e63;border-radius:6px;'><h2 style='margin:0 0 8px;font-size:16px;color:#e91e63;'>📖 词汇表</h2><div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;'>${vocabHTML}</div></section>`:''}
        <footer style='text-align:center;margin-top:24px;padding-top:12px;border-top:1px solid #ddd;font-size:11px;color:#666;'>🌟 YomuTomo 自动生成 · 继续加油！</footer>`;
    document.body.appendChild(wrap);
    return wrap;
}
