import numpy as np

def tone_bursts(sample_rate, duration_s, bursts, noise_amp=0.0, seed=0):
    n = int(duration_s * sample_rate)
    sig = np.zeros(n, dtype=np.float32)
    for (start_s, freq, dur_s, amp) in bursts:
        i0 = int(start_s * sample_rate)
        i1 = min(n, int((start_s + dur_s) * sample_rate))
        seg = np.arange(i1 - i0) / sample_rate
        sig[i0:i1] += (amp * np.sin(2 * np.pi * freq * seg)).astype(np.float32)
    if noise_amp > 0:
        rng = np.random.default_rng(seed)
        sig += (noise_amp * rng.standard_normal(n)).astype(np.float32)
    return sig
