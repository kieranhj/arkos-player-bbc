#!/usr/bin/env python3
"""Render a stream of SN76489 register writes to a WAV, for listening tests.

The port has two ways of driving the sound chip and no way to compare them by
ear without a machine in front of you. This renders either to a file:

    python tools/sn2wav.py build/cut.vgm -o shipping.wav
    python tools/sn2wav.py capture.snf  -o runtime.wav --seconds 60

Inputs:
  *.vgm   a VGM file (SN76489 only) - the format the offline chain produces
  *.snf   a flat capture of per-frame writes, which is what you get by running
          a player in a simulator and watching &FE4F. See write_snf().

The chip model is the BBC's: SN76489 at 4 MHz, 15-bit LFSR, feedback on bits
0 and 1 - all read out of the VGM header rather than assumed. Tone channels are
rendered analytically per frame with 4x oversampling (registers only change on
frame boundaries, so a frame is a constant-frequency square), and the noise
LFSR is stepped for real.
"""

import argparse
import os
import struct
import sys
import wave

import numpy as np

SNF_MAGIC = b'SNF1'


# ----------------------------------------------------------------- inputs
def read_vgm(path):
    """Returns (frames, frame_rate) where frames is a list of write-byte lists."""
    d = open(path, 'rb').read()
    if d[:4] != b'Vgm ':
        raise SystemExit('%s is not a VGM' % path)
    clock = struct.unpack('<I', d[0x0C:0x10])[0]
    feedback = struct.unpack('<H', d[0x28:0x2A])[0] or 0x0009
    width = d[0x2A] or 16
    rate = struct.unpack('<I', d[0x24:0x28])[0] or 50
    i = 0x34 + struct.unpack('<I', d[0x34:0x38])[0]
    frames, cur = [], []
    while i < len(d):
        c = d[i]
        if c == 0x50:                       # SN76489 write
            cur.append(d[i + 1])
            i += 2
        elif c in (0x62, 0x63):             # wait one 60 Hz / 50 Hz frame
            frames.append(cur)
            cur = []
            i += 1
        elif c == 0x61:                     # wait n samples
            frames.append(cur)
            cur = []
            i += 3
        elif 0x70 <= c <= 0x7F:             # short wait
            frames.append(cur)
            cur = []
            i += 1
        elif c == 0x66:                     # end of data
            break
        else:
            i += 1
    if cur:
        frames.append(cur)
    return frames, rate, clock, feedback, width


def read_snf(path):
    d = open(path, 'rb').read()
    if d[:4] != SNF_MAGIC:
        raise SystemExit('%s is not an SNF capture' % path)
    n, rate, clock, feedback, width = struct.unpack('<IIIHH', d[4:20])
    frames, o = [], 20
    for _ in range(n):
        c = d[o]
        o += 1
        frames.append(list(d[o:o + c]))
        o += c
    return frames, rate, clock, feedback, width


def write_snf(path, frames, rate=50, clock=4000000, feedback=3, width=15):
    """Write a per-frame capture. Used by the simulator harnesses."""
    out = bytearray(SNF_MAGIC)
    out += struct.pack('<IIIHH', len(frames), rate, clock, feedback, width)
    for f in frames:
        out.append(len(f))
        out += bytes(f)
    open(path, 'wb').write(out)


# ------------------------------------------------------------------ chip
class SN76489(object):
    """Enough of the chip to listen to. Tones are rendered per frame;
    the noise LFSR is stepped one shift at a time."""

    # 4-bit attenuation, 2 dB a step, 15 = off
    ATTEN = np.array([10.0 ** (-0.1 * 2 * a) for a in range(15)] + [0.0])

    def __init__(self, clock=4000000, feedback=0x3, width=15, rate=44100,
                 oversample=4):
        self.tick_hz = clock / 16.0         # the internal counter rate
        self.feedback = feedback
        self.width = width
        self.rate = rate
        self.os = oversample
        self.ticks_per_sample = self.tick_hz / (rate * oversample)

        self.tone = [1, 1, 1]               # 10-bit periods
        self.vol = [15, 15, 15, 15]         # attenuations
        self.noise_ctl = 0
        self.latch = 0                      # 0-3, which register a data byte hits
        self.latch_is_vol = True

        self.phase = [0.0, 0.0, 0.0]        # tone counters, in ticks
        self.noise_phase = 0.0
        self.lfsr = 1 << (width - 1)

    def write(self, b):
        if b & 0x80:
            self.latch = (b >> 5) & 3
            self.latch_is_vol = bool((b >> 4) & 1)
            if self.latch_is_vol:
                self.vol[self.latch] = b & 0x0F
            elif self.latch == 3:
                self.noise_ctl = b & 0x0F
                self.lfsr = 1 << (self.width - 1)      # a write resets the LFSR
            else:
                self.tone[self.latch] = (self.tone[self.latch] & 0x3F0) | (b & 0x0F)
        else:
            if self.latch_is_vol:
                self.vol[self.latch] = b & 0x0F
            elif self.latch == 3:
                self.noise_ctl = b & 0x0F
            else:
                self.tone[self.latch] = (self.tone[self.latch] & 0x00F) | ((b & 0x3F) << 4)

    def _noise_step_ticks(self):
        nf = self.noise_ctl & 3
        if nf == 3:
            n = self.tone[2] or 1
            return 2.0 * n                  # clocked by tone generator 3
        return float([512, 1024, 2048][nf])

    def render_frame(self, nsamples):
        """nsamples output samples at self.rate, with the registers as they are."""
        m = nsamples * self.os
        step = self.ticks_per_sample
        acc = np.zeros(m, dtype=np.float64)

        for ch in range(3):
            a = self.ATTEN[self.vol[ch]]
            n = self.tone[ch] or 1
            x = self.phase[ch] + np.arange(m, dtype=np.float64) * step
            if a > 0.0:
                # the output flips every n ticks
                acc += a * (1.0 - 2.0 * (np.floor(x / n).astype(np.int64) & 1))
            self.phase[ch] = (self.phase[ch] + m * step) % (2 * n)

        a = self.ATTEN[self.vol[3]]
        sp = self._noise_step_ticks()
        x = self.noise_phase + np.arange(m, dtype=np.float64) * step
        idx = np.floor(x / sp).astype(np.int64)
        first, last = idx[0], idx[-1]
        nsteps = int(last - first) + 1
        bits = np.empty(nsteps, dtype=np.float64)
        white = bool(self.noise_ctl & 4)
        for i in range(nsteps):
            bits[i] = 1.0 if (self.lfsr & 1) else -1.0
            if white:
                fb = bin(self.lfsr & self.feedback).count('1') & 1
            else:
                fb = self.lfsr & 1
            self.lfsr = (self.lfsr >> 1) | (fb << (self.width - 1))
        if a > 0.0:
            acc += a * bits[idx - first]
        self.noise_phase += m * step
        # keep the noise phase from growing without bound
        if self.noise_phase > 1e12:
            self.noise_phase = self.noise_phase % sp

        return acc.reshape(nsamples, self.os).mean(axis=1)


# ----------------------------------------------------------------- render
def render(frames, frame_rate, clock, feedback, width, rate, seconds=None,
           oversample=4):
    chip = SN76489(clock, feedback, width, rate, oversample)
    if seconds:
        frames = frames[:int(seconds * frame_rate)]
    per_frame = rate / float(frame_rate)
    out = []
    carried = 0.0
    for wr in frames:
        for b in wr:
            chip.write(b)
        carried += per_frame
        n = int(carried)
        carried -= n
        if n:
            out.append(chip.render_frame(n))
    if not out:
        raise SystemExit('nothing to render')
    return np.concatenate(out)


def write_wav(path, samples, rate):
    peak = np.max(np.abs(samples)) or 1.0
    pcm = np.clip(samples / peak * 0.89, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input', help='a .vgm or a .snf capture')
    ap.add_argument('-o', '--output', help='the .wav to write')
    ap.add_argument('--rate', type=int, default=44100)
    ap.add_argument('--seconds', type=float, default=0,
                    help='render only the first N seconds')
    ap.add_argument('--start', type=float, default=0,
                    help='skip the first N seconds of the tune')
    ap.add_argument('--oversample', type=int, default=4)
    args = ap.parse_args()

    if args.input.lower().endswith('.snf'):
        frames, frate, clock, fb, width = read_snf(args.input)
    else:
        frames, frate, clock, fb, width = read_vgm(args.input)
    print('%s: %d frames at %d Hz (%.1f s), SN clock %d, %d-bit LFSR'
          % (os.path.basename(args.input), len(frames), frate,
             len(frames) / float(frate), clock, width))

    if args.start:
        # The chip is walked through the skipped frames so its state is right,
        # then that state is re-emitted as a synthetic first frame.
        skip = int(args.start * frate)
        chip = SN76489(clock, fb, width, args.rate, 1)
        for wr in frames[:skip]:
            for b in wr:
                chip.write(b)
        prime = []
        for c in range(3):
            prime.append(0x80 | (c << 5) | (chip.tone[c] & 0x0F))
            prime.append((chip.tone[c] >> 4) & 0x3F)
            prime.append(0x90 | (c << 5) | chip.vol[c])
        prime.append(0xE0 | chip.noise_ctl)
        prime.append(0xF0 | chip.vol[3])
        frames = [prime] + frames[skip:]

    s = render(frames, frate, clock, fb, width, args.rate,
               args.seconds or None, args.oversample)
    out = args.output or (os.path.splitext(args.input)[0] + '.wav')
    write_wav(out, s, args.rate)
    print('%s: %.1f s, %d samples at %d Hz' % (out, len(s) / float(args.rate),
                                               len(s), args.rate))


if __name__ == '__main__':
    sys.exit(main())
