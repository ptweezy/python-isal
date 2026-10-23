"""Decompress outputs near the start size of the decompressobj output buffer.

Decompress.decompress() expects the output size of the last call that
consumed input, scaled down when the call has less input than that call
consumed, at most 1 MiB. The output buffer starts at that size plus a
quarter, at least 16 KiB and at most max_length. The first call and calls
after the end of the stream start at 16 KiB. A call that consumes no input,
such as decompress(b""), keeps the previous sizes.
"""
import gzip
import itertools
import zlib
from pathlib import Path

from isal import isal_zlib

import pytest

DATA_DIR = Path(__file__).parent / "data"
with gzip.open(str(DATA_DIR / "test.fastq.gz"), mode="rb") as file_h:
    FASTQ = file_h.read()
# At compression level 1, b"x" compresses about 100 times or more, FASTQ
# less than 2 times and gzipped data not at all.
X = b"x"
GZIPPED = (DATA_DIR / "test.fastq.gz").read_bytes()
ZDICT = FASTQ[:32 * 1024]

KiB = 1024
MiB = 1024 * KiB
# Consecutive messages as (source, output size). None is a call with empty
# input.
MESSAGES = [
    # Equal messages, like the websocket messages in aiohttp's benchmark.
    [(X, 512 * KiB)] * 3,
    # The same data at growing and shrinking sizes. After 100 bytes, 2 MiB
    # expects at most 100 bytes, so it starts at 16 KiB and grows.
    [(FASTQ, 64 * KiB), (FASTQ, 512 * KiB), (FASTQ, 100), (FASTQ, 2 * MiB),
     (FASTQ, 1), (FASTQ, 4 * KiB)],
    # After 1 MiB or more, these expect 1 MiB and start at 1.25 MiB. They
    # fill it exactly, exceed it by one byte and fall one byte short.
    [(X, 1 * MiB), (X, 1280 * KiB), (X, 1280 * KiB + 1), (X, 1280 * KiB - 1),
     (X, 4 * MiB)],
    # b"x" has far less input than the gzipped data before it, so it expects
    # little and starts at 16 KiB. It fills 16 KiB exactly, exceeds it by one
    # byte and falls one byte short.
    [(GZIPPED, 1 * KiB), (X, 16 * KiB), (GZIPPED, 1 * KiB), (X, 16 * KiB + 1),
     (GZIPPED, 1 * KiB), (X, 16 * KiB - 1)],
    # A rising ratio: the buffer grows from a start size between the limits.
    [(GZIPPED, 512 * KiB), (FASTQ, 512 * KiB), (X, 4 * MiB)],
    # A falling ratio: the start size is far above the output.
    [(X, 1 * MiB), (GZIPPED, 64 * KiB), (X, 4 * MiB), (FASTQ, 512 * KiB),
     (GZIPPED, 1)],
    # Small after big and big after small. Empty input keeps the previous
    # sizes. After empty output, the next call starts at 16 KiB.
    [(X, 2 * MiB), None, (X, 2 * MiB), (X, 1), (X, 100), (X, 2 * MiB),
     (X, 0), (X, 2 * MiB), None],
]
# Smaller than, equal to and larger than the start sizes above, such as
# 16 KiB, 640 KiB for 512 KiB of b"x" and 1.25 MiB. aiohttp uses its maximum
# message size plus one.
MAX_LENGTHS = [0, 10000, 16 * KiB, 80 * KiB, 640 * KiB, 1280 * KiB,
               4 * MiB + 1]
# Compression wbits, decompression wbits and zdict. 47 detects zlib or gzip.
FORMATS = [(-15, -15, None), (15, 47, None), (31, 47, None),
           (-15, -15, ZDICT), (15, 15, ZDICT)]


def sync_flushed_stream(messages, wbits, zdict):
    """Return the messages, their compressed inputs and the stream end."""
    kwargs = {"zdict": zdict} if zdict else {}
    compressor = zlib.compressobj(1, wbits=wbits, **kwargs)
    plain = []
    inputs = []
    offsets = {}
    for message in messages:
        if message is None:
            plain.append(b"")
            inputs.append(b"")
            continue
        source, size = message
        offset = offsets.get(source, 0)
        data = (source[offset:] + source * (size // len(source) + 1))[:size]
        offsets[source] = (offset + size) % len(source)
        plain.append(data)
        inputs.append(compressor.compress(data) +
                      compressor.flush(zlib.Z_SYNC_FLUSH))
    return plain, inputs, compressor.flush()


def decompress_all(decompressor, data, max_length):
    outputs = [decompressor.decompress(data, max_length)]
    # isal_zlib can take in all input before it returns all output, so
    # continue while outputs fill max_length, not while unconsumed_tail has
    # data.
    while max_length and len(outputs[-1]) == max_length:
        outputs.append(decompressor.decompress(decompressor.unconsumed_tail,
                                               max_length))
    assert decompressor.unconsumed_tail == b""
    return outputs


@pytest.mark.parametrize(["messages", "max_length", "stream_format"],
                         list(itertools.product(MESSAGES, MAX_LENGTHS,
                                                FORMATS[:1])) +
                         list(itertools.product(MESSAGES, [0, 10000],
                                                FORMATS[1:])))
def test_decompressobj_output_sizes(messages, max_length, stream_format):
    compress_wbits, wbits, zdict = stream_format
    plain, inputs, end = sync_flushed_stream(messages, compress_wbits, zdict)
    kwargs = {"zdict": zdict} if zdict else {}
    decompressor = isal_zlib.decompressobj(wbits=wbits, **kwargs)
    zlib_decompressor = zlib.decompressobj(wbits=wbits, **kwargs)
    for message, data in zip(plain, inputs):
        outputs = decompress_all(decompressor, data, max_length)
        assert b"".join(outputs) == message
        assert outputs == decompress_all(zlib_decompressor, data, max_length)
    assert decompressor.decompress(end + b"unused") == b""
    assert decompressor.eof
    assert decompressor.unused_data == b"unused"


@pytest.mark.parametrize(["messages", "max_peak"], [
    # The second of two equal messages fits in its first buffer of 640 KiB.
    # Doubling from 16 KiB fills 512 KiB exactly and grows to 1 MiB.
    ([(X, 512 * KiB), (X, 512 * KiB)], 768 * KiB),
    # A small message after a big one of the same data starts at 16 KiB.
    ([(X, 1 * MiB), (X, 100)], 64 * KiB),
    # Gzipped data has more input than the 4 MiB of b"x" before it, so it
    # expects the maximum of 1 MiB and starts at 1.25 MiB for 64 KiB of
    # output.
    ([(X, 4 * MiB), (GZIPPED, 64 * KiB)], 2 * MiB),
    # An empty call in between, like aiohttp's check for pending output,
    # keeps the sizes, so the second message still fits in its first buffer.
    ([(X, 512 * KiB), None, (X, 512 * KiB)], 768 * KiB),
    # Gzipped data after a small message of b"x" expects at most that
    # message's 16 KiB, so it starts at 20 KiB instead of 1.25 MiB.
    ([(X, 16 * KiB), (GZIPPED, 16 * KiB)], 64 * KiB),
])
def test_decompressobj_output_buffer_peak(messages, max_peak):
    # PyPy has no tracemalloc.
    tracemalloc = pytest.importorskip("tracemalloc")
    if tracemalloc.is_tracing():
        pytest.skip("tracemalloc is already tracing")
    plain, inputs, _ = sync_flushed_stream(messages, -15, None)
    decompressor = isal_zlib.decompressobj(wbits=-15)
    for message, data in zip(plain[:-1], inputs[:-1]):
        assert decompressor.decompress(data, 4 * MiB + 1) == message
    tracemalloc.start()
    try:
        output = decompressor.decompress(inputs[-1], 4 * MiB + 1)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert output == plain[-1]
    assert peak < max_peak


def test_decompressobj_output_buffer_peak_after_eof():
    tracemalloc = pytest.importorskip("tracemalloc")
    if tracemalloc.is_tracing():
        pytest.skip("tracemalloc is already tracing")
    plain, inputs, end = sync_flushed_stream([(X, 1 * MiB)], -15, None)
    decompressor = isal_zlib.decompressobj(wbits=-15)
    assert decompressor.decompress(inputs[0] + end) == plain[0]
    assert decompressor.eof
    trailing = b"\0" * (64 * KiB)
    tracemalloc.start()
    try:
        # Data after the end of the stream goes to unused_data. The output
        # buffer starts at 16 KiB, not at the size of the previous output.
        output = decompressor.decompress(trailing)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert output == b""
    assert decompressor.unused_data == trailing
    assert peak < 256 * KiB
