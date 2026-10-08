/*
 * 自由回忆录音组件(可复用)。
 *
 * 用法:
 *   mountRecallRecorder(document.getElementById('box'), {
 *     sessionId: '...', kind: 'baseline',
 *     onDone: (recall) => { ... }        // 转写完成回调,可选
 *   });
 *
 * 行为:浏览器 MediaRecorder 录音 -> 上传到 /api/session/{sid}/recall
 * -> 轮询同一端点直到 status=done|failed。音频不经过任何第三方服务。
 */
(function (global) {
  'use strict';

  // 优先 webm/opus(Chrome/Firefox/Edge);Safari 只支持 mp4。
  const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];
  const POLL_INTERVAL_MS = 2000;
  const POLL_TIMEOUT_MS = 10 * 60 * 1000;      // 转写超过 10 分钟视为异常

  function pickMimeType() {
    if (typeof MediaRecorder === 'undefined') return null;
    for (const m of MIME_CANDIDATES) {
      if (MediaRecorder.isTypeSupported(m)) return m;
    }
    return '';                                  // 交给浏览器选默认值
  }

  function fmtTime(sec) {
    const m = Math.floor(sec / 60), s = sec % 60;
    return m + ':' + String(s).padStart(2, '0');
  }

  function mountRecallRecorder(el, opts) {
    const { sessionId, kind = 'baseline', onDone = null } = opts || {};
    if (!sessionId) throw new Error('mountRecallRecorder: sessionId is required');

    el.innerHTML = [
      '<div class="recallRecorder">',
      '  <div class="recallStatus" data-role="status">Ready to record.</div>',
      '  <div class="recallTimer" data-role="timer">0:00</div>',
      '  <div class="recallControls">',
      '    <button type="button" data-role="start">Start recording</button>',
      '    <button type="button" data-role="stop" disabled>Stop and submit</button>',
      '  </div>',
      '  <audio data-role="playback" controls hidden></audio>',
      '  <div class="recallTranscript" data-role="transcript" hidden></div>',
      '</div>',
    ].join('\n');

    const $ = (role) => el.querySelector('[data-role="' + role + '"]');
    const statusEl = $('status'), timerEl = $('timer');
    const startBtn = $('start'), stopBtn = $('stop');
    const playbackEl = $('playback'), transcriptEl = $('transcript');

    let recorder = null, chunks = [], stream = null;
    let seconds = 0, timerId = null;

    function setStatus(msg) { statusEl.textContent = msg; }

    function startTimer() {
      seconds = 0;
      timerEl.textContent = '0:00';
      timerId = setInterval(() => { seconds += 1; timerEl.textContent = fmtTime(seconds); }, 1000);
    }

    function stopTimer() { if (timerId) { clearInterval(timerId); timerId = null; } }

    function releaseStream() {
      if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
    }

    async function start() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setStatus('This browser does not support audio recording.');
        return;
      }
      const mimeType = pickMimeType();
      if (mimeType === null) {
        setStatus('This browser does not support audio recording.');
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (e) {
        // NotAllowedError 是用户拒绝授权,其余多为没有可用麦克风
        setStatus(e && e.name === 'NotAllowedError'
          ? 'Microphone permission was denied. Please allow access and try again.'
          : 'No microphone available.');
        return;
      }

      chunks = [];
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorder.ondataavailable = (ev) => { if (ev.data && ev.data.size > 0) chunks.push(ev.data); };
      recorder.onstop = () => { stopTimer(); releaseStream(); upload(); };
      // 每秒切一片:录音中途页面崩溃时已产生的数据不会全部丢失
      recorder.start(1000);

      startTimer();
      startBtn.disabled = true;
      stopBtn.disabled = false;
      playbackEl.hidden = true;
      transcriptEl.hidden = true;
      setStatus('Recording. Take your time.');
    }

    function stop() {
      if (!recorder || recorder.state === 'inactive') return;
      stopBtn.disabled = true;
      setStatus('Finishing up…');
      recorder.stop();
    }

    async function upload() {
      const type = (chunks[0] && chunks[0].type) || 'audio/webm';
      const blob = new Blob(chunks, { type });
      if (!blob.size) {
        setStatus('Nothing was recorded. Please try again.');
        startBtn.disabled = false;
        return;
      }

      playbackEl.src = URL.createObjectURL(blob);
      playbackEl.hidden = false;

      const ext = type.indexOf('mp4') >= 0 ? 'm4a' : 'webm';
      const form = new FormData();
      form.append('audio', blob, 'recall.' + ext);

      setStatus('Uploading…');
      try {
        const res = await fetch(
          '/api/session/' + encodeURIComponent(sessionId) + '/recall?kind=' + encodeURIComponent(kind),
          { method: 'POST', body: form }
        );
        if (!res.ok) throw new Error('upload failed: HTTP ' + res.status);
      } catch (e) {
        // 音频还在内存里,允许直接重试,不必重录
        setStatus('Upload failed. Press Stop and submit again to retry.');
        stopBtn.disabled = false;
        return;
      }

      setStatus('Transcribing…');
      poll(Date.now());
    }

    async function poll(startedAt) {
      if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
        setStatus('Transcription is taking longer than expected. Please tell the researcher.');
        startBtn.disabled = false;
        return;
      }
      try {
        const res = await fetch(
          '/api/session/' + encodeURIComponent(sessionId) + '/recall?kind=' + encodeURIComponent(kind)
        );
        if (res.ok) {
          const row = await res.json();
          if (row.status === 'done') {
            setStatus('Saved.');
            transcriptEl.textContent = row.transcript || '';
            transcriptEl.hidden = false;
            startBtn.disabled = false;
            if (onDone) onDone(row);
            return;
          }
          if (row.status === 'failed') {
            // 音频已落盘,研究者可在后台用 /recall/retranscribe 重跑
            setStatus('Recording saved, but transcription failed. The audio is stored.');
            startBtn.disabled = false;
            if (onDone) onDone(row);
            return;
          }
        }
      } catch (e) { /* 网络抖动:下一轮继续轮询 */ }
      setTimeout(() => poll(startedAt), POLL_INTERVAL_MS);
    }

    startBtn.addEventListener('click', start);
    stopBtn.addEventListener('click', stop);

    return { start, stop, destroy: () => { stopTimer(); releaseStream(); } };
  }

  global.mountRecallRecorder = mountRecallRecorder;
})(window);
