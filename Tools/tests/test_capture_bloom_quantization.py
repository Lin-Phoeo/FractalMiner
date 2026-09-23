"""Dependency-free CPU references for the captured Bloom's unsigned float stores.

This checks boundaries and the source-mode contract, not GPU execution. Unity's
QuantizeProbe and comparisons against events 1121..1185 remain the GPU gates.
Run: python -m unittest discover -s Tools/tests -p test_capture_bloom_quantization.py
"""
import bisect
import math
from pathlib import Path
import random
import struct
import unittest


def float32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def quantize_bits(value, mantissa_bits, mode):
    """Float32-bit implementation corresponding to the HLSL fallback."""
    bits = struct.unpack('<I', struct.pack('<f', value))[0]
    source_exponent = (bits >> 23) & 255
    mantissa = bits & 0x7fffff
    if source_exponent == 255 and mantissa:
        return math.nan
    if bits & 0x80000000:
        return 0.0
    if source_exponent == 255:
        return math.inf

    def reduce(significand, shift):
        high = significand >> shift
        if mode == 'rtz':
            return high
        remainder = significand & ((1 << shift) - 1)
        halfway = 1 << (shift - 1)
        return high + int(remainder > halfway or
                          (remainder == halfway and high & 1))

    exponent = source_exponent - 112
    if exponent <= 0:
        if exponent < -mantissa_bits:
            return 0.0
        return math.ldexp(reduce(0x800000 | mantissa,
                                24 - mantissa_bits - exponent), -14 - mantissa_bits)
    max_value = math.ldexp(2 - 2 ** -mantissa_bits, 15)
    if exponent >= 31:
        return max_value if mode == 'rtz' else math.inf
    rounded = reduce(mantissa, 23 - mantissa_bits)
    if rounded == (1 << mantissa_bits):
        rounded = 0
        exponent += 1
    if exponent >= 31:
        return max_value if mode == 'rtz' else math.inf
    return math.ldexp(1 + rounded / (1 << mantissa_bits), exponent - 15)


def representable_values(mantissa_bits):
    """Independent arithmetic enumeration; list index equals the packed code."""
    count = 1 << mantissa_bits
    return [math.ldexp(m / count, -14) for m in range(count)] + [
        math.ldexp(1 + m / count, e - 15)
        for e in range(1, 31) for m in range(count)]


class CapturedBloomQuantizationTests(unittest.TestCase):
    def test_all_exact_values_remain_exact(self):
        for mantissa in (5, 6):
            for value in representable_values(mantissa):
                for mode in ('rtz', 'rne'):
                    self.assertEqual(quantize_bits(value, mantissa, mode), value)

    def test_every_midpoint_distinguishes_truncation_and_even_ties(self):
        for mantissa in (5, 6):
            values = representable_values(mantissa)
            for code, (low, high) in enumerate(zip(values, values[1:])):
                midpoint = (low + high) / 2
                self.assertEqual(quantize_bits(midpoint, mantissa, 'rtz'), low)
                self.assertEqual(quantize_bits(midpoint, mantissa, 'rne'),
                                 high if code & 1 else low)

    def test_random_rtz_matches_independent_ordered_reference(self):
        randomizer = random.Random(6411)
        for mantissa in (5, 6):
            values = representable_values(mantissa)
            for _ in range(2000):
                value = float32(2 ** randomizer.uniform(-25, 18))
                expected = values[max(0, bisect.bisect_right(values, value) - 1)]
                self.assertEqual(quantize_bits(value, mantissa, 'rtz'), expected)

    def test_subnormal_overflow_and_special_values(self):
        for mantissa in (5, 6):
            minimum = 2 ** (-14 - mantissa)
            maximum = representable_values(mantissa)[-1]
            for mode in ('rtz', 'rne'):
                self.assertEqual(quantize_bits(minimum / 2, mantissa, mode), 0)
                self.assertEqual(quantize_bits(-1, mantissa, mode), 0)
                self.assertEqual(quantize_bits(-math.inf, mantissa, mode), 0)
                self.assertEqual(quantize_bits(math.inf, mantissa, mode), math.inf)
                self.assertTrue(math.isnan(quantize_bits(math.nan, mantissa, mode)))
            self.assertEqual(quantize_bits(65536, mantissa, 'rtz'), maximum)
            self.assertEqual(quantize_bits(65536, mantissa, 'rne'), math.inf)

    def test_shader_mode_contract_keeps_both_modes_and_probe(self):
        root = Path(__file__).resolve().parents[2]
        shader = (root / 'Assets/EndfieldShaderPack/EndfieldCapturedBloom.compute').read_text('utf-8')
        runtime = (root / 'Assets/EndfieldShaderPack/EndfieldCapturedBloom.cs').read_text('utf-8')
        self.assertIn('#pragma kernel QuantizeProbe', shader)
        self.assertIn('RoundTowardZero = 2', runtime)
        self.assertIn('RoundToNearestEven = 1', runtime)
        self.assertIn('RoundingMode { get; set; }', runtime)
        self.assertIn('_QuantizeOutput == 2', shader)


if __name__ == '__main__':
    unittest.main()
