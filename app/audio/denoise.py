import logging
import struct

import numpy as np

logger = logging.getLogger(__name__)

RNNOISE_AVAILABLE = False
_rnnoise = None

try:
    import rnnoise as _rnnoise_lib

    _rnnoise = _rnnoise_lib
    RNNOISE_AVAILABLE = True
    logger.info("RNNoise loaded — audio denoising enabled")
except ImportError:
    logger.warning("rnnoise-python not available — audio denoising disabled (pass-through)")


RNNOISE_SAMPLE_RATE = 48000
RNNOISE_FRAME_SIZE = 480  # 10 ms at 48 kHz


def _resample(audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return audio
    from scipy.signal import resample

    num_samples = int(len(audio) * to_rate / from_rate)
    return resample(audio, num_samples)


def denoise_audio(audio_bytes: bytes, sample_rate: int = 16000) -> bytes:
    if not RNNOISE_AVAILABLE:
        return audio_bytes

    try:
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)

        if len(samples) == 0:
            return audio_bytes

        upsampled = _resample(samples, sample_rate, RNNOISE_SAMPLE_RATE)

        pad_len = RNNOISE_FRAME_SIZE - (len(upsampled) % RNNOISE_FRAME_SIZE)
        if pad_len != RNNOISE_FRAME_SIZE:
            upsampled = np.concatenate([upsampled, np.zeros(pad_len, dtype=np.float32)])

        denoised_frames = []
        for i in range(0, len(upsampled), RNNOISE_FRAME_SIZE):
            frame = upsampled[i : i + RNNOISE_FRAME_SIZE]
            processed = _rnnoise.process(frame.tobytes())
            denoised_frames.append(np.frombuffer(processed, dtype=np.int16).astype(np.float32))

        denoised = np.concatenate(denoised_frames)

        downsampled = _resample(denoised, RNNOISE_SAMPLE_RATE, sample_rate)

        original_length = len(np.frombuffer(audio_bytes, dtype=np.int16))
        downsampled = downsampled[:original_length]

        result = downsampled.astype(np.int16)
        return result.tobytes()

    except Exception:
        logger.exception("Denoising failed — returning original audio")
        return audio_bytes
