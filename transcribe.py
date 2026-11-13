# -*- coding: utf-8 -*-
"""
本地语音转写(faster-whisper)。

设计要点:
- 不调用任何外部 API:受试者音频不出本机,避免第三方披露带来的伦理审查问题;
- 模型懒加载并全局复用:首次调用会下载权重,之后常驻内存;
- 自行解码音频:浏览器 MediaRecorder 产出的 WebM 是"直播流"格式,头部没有
  有效时长(duration),直接交给解码器常常只读到第一个 chunk 就停止,
  导致 20 多秒的录音只转写出几个词。这里显式遍历所有 packet 解码成
  单声道 16kHz 波形再喂给模型,绕开对容器时长的依赖。
- 与 agent.py 一致,仅从环境变量读配置。

环境变量:
  WHISPER_MODEL         模型大小,默认 small(tiny/base/small/medium/large-v3)
  WHISPER_DEVICE        cpu(默认)或 cuda
  WHISPER_COMPUTE_TYPE  int8(默认,CPU 友好)/ float16(GPU)
  WHISPER_LANGUAGE      强制语种,默认 en;留空则自动识别
  WHISPER_VAD           1(默认)启用静音过滤;自由回忆停顿多,若怀疑漏词可设 0
"""
import os
import threading

MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "en") or None
USE_VAD = os.environ.get("WHISPER_VAD", "1") != "0"

SAMPLE_RATE = 16000          # Whisper 的输入采样率

_model = None
_model_lock = threading.Lock()


def _get_model():
    """懒加载并复用模型。加载耗时较长(首次含下载),用锁避免并发重复加载。"""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise RuntimeError(
                    "faster-whisper is not installed. Run: pip install -r requirements.txt"
                ) from e
            _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    return _model


def decode_audio(path: str):
    """把任意音频文件解码成 float32 单声道 16kHz numpy 波形。

    显式遍历容器里的每一个 packet,不依赖头部声明的时长 —— 这正是
    MediaRecorder 录音会被截断的原因。
    """
    import av
    import numpy as np

    with av.open(path, mode="r") as container:
        if not container.streams.audio:
            raise RuntimeError("file contains no audio stream")
        stream = container.streams.audio[0]
        resampler = av.audio.resampler.AudioResampler(
            format="s16", layout="mono", rate=SAMPLE_RATE,
        )
        chunks = []
        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                chunks.append(resampled.to_ndarray().reshape(-1))
        # resampler 内部可能还缓冲了最后一点数据,flush 出来
        for resampled in resampler.resample(None):
            chunks.append(resampled.to_ndarray().reshape(-1))

    if not chunks:
        raise RuntimeError("no audio frames could be decoded")
    pcm = np.concatenate(chunks).astype("float32") / 32768.0
    return pcm


def transcribe_file(path: str) -> str:
    """把音频文件转写为纯文本。失败时抛 RuntimeError,由调用方记入 free_recalls.error。"""
    if not os.path.exists(path):
        raise RuntimeError(f"audio file not found: {path}")
    if os.path.getsize(path) == 0:
        raise RuntimeError("audio file is empty")

    audio = decode_audio(path)
    duration = len(audio) / SAMPLE_RATE
    if duration < 0.5:
        raise RuntimeError(f"decoded audio is only {duration:.2f}s long")

    model = _get_model()
    segments, _info = model.transcribe(
        audio, language=LANGUAGE, vad_filter=USE_VAD, beam_size=5,
    )
    text = " ".join(seg.text.strip() for seg in segments if seg.text and seg.text.strip())
    text = text.strip()
    if not text:
        raise RuntimeError("transcription produced no text (silent or unintelligible audio)")
    return text


if __name__ == "__main__":
    # 本地自测: python transcribe.py path/to/audio.webm
    import sys
    if len(sys.argv) != 2:
        print("usage: python transcribe.py <audio-file>")
        raise SystemExit(2)
    pcm = decode_audio(sys.argv[1])
    print(f"[decoded {len(pcm) / SAMPLE_RATE:.1f}s of audio]")
    print(transcribe_file(sys.argv[1]))
