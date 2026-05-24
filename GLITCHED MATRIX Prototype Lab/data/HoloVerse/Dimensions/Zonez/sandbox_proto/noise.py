from __future__ import annotations

import math


def _hash_2d(x: int, y: int, seed: int) -> float:
    n = x * 374761393 + y * 668265263 + seed * 69069
    n = (n ^ (n >> 13)) * 1274126177
    n = n ^ (n >> 16)
    return (n & 0xFFFFFFFF) / 0xFFFFFFFF


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def value_noise_2d(x: float, y: float, seed: int) -> float:
    x0 = math.floor(x)
    y0 = math.floor(y)
    x1 = x0 + 1
    y1 = y0 + 1

    sx = _smoothstep(x - x0)
    sy = _smoothstep(y - y0)

    n00 = _hash_2d(x0, y0, seed)
    n10 = _hash_2d(x1, y0, seed)
    n01 = _hash_2d(x0, y1, seed)
    n11 = _hash_2d(x1, y1, seed)

    ix0 = n00 + (n10 - n00) * sx
    ix1 = n01 + (n11 - n01) * sx
    return ix0 + (ix1 - ix0) * sy


def fractal_noise_2d(x: float, y: float, seed: int, octaves: int = 4) -> float:
    total = 0.0
    amplitude = 1.0
    frequency = 1.0
    amplitude_sum = 0.0

    for octave in range(octaves):
        total += value_noise_2d(x * frequency, y * frequency, seed + octave * 97) * amplitude
        amplitude_sum += amplitude
        amplitude *= 0.5
        frequency *= 2.0

    return total / max(amplitude_sum, 1e-6)
