document.querySelector('form').addEventListener('submit', function (e) {
    const apiKey = document.getElementById('api-key').value;
    if (!apiKey) {
        showToast('请输入OpenAI API Key', 'warning');
        e.preventDefault();
        return;
    }
    // 可以在这里验证key，但暂时跳过
});

document.getElementById('record-btn').addEventListener('click', () => {
    finalTranscript = '';
    recognition.start();
    document.getElementById('record-btn').disabled = true;
    document.getElementById('stop-btn').disabled = false;
    document.getElementById('result').innerHTML = '正在录音...';
    document.getElementById('highlight-text').innerHTML = '{{ original }}';
});

document.getElementById('stop-btn').addEventListener('click', () => {
    recognition.stop();
    document.getElementById('record-btn').disabled = false;
    document.getElementById('stop-btn').disabled = true;
});

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
    document.getElementById('result').innerHTML = `<p>识别文本：${finalTranscript}<i style="color:#7f8c8d">${interimTranscript}</i></p>`;

    // 高亮匹配部分
    if (finalTranscript) {
        highlightText(finalTranscript);
    }
};

function highlightText(recognized) {
    let highlightText = document.getElementById('highlight-text');
    let text = '{{ original }}';
    let start = text.indexOf(recognized);
    if (start !== -1) {
        let before = text.substring(0, start);
        let match = text.substring(start, start + recognized.length);
        let after = text.substring(start + recognized.length);
        highlightText.innerHTML = `${before}<span class="highlight">${match}</span>${after}`;
    } else {
        highlightText.innerHTML = text;
    }
}

function removeWord(btn) {
    btn.parentElement.remove();
}
