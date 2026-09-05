#!/usr/bin/env python3
"""What each music format costs on a BBC, over the demo discs' four tunes.

Six ways to play the same song on an SN76489, measured the same way:

  AKL, AKY, AKM   this library - a tracker replay plus lib/ay2sn.asm
  VGC, VGI   simondotm's register-log formats and players, from
             BEEB/Repos/vgm-player-bbc, fed by ym2sn.py
  AKG        Arkos's other tracker format, DATA SIZE ONLY - there is no
             6502 player for it anywhere

Every cycle figure is one call of the player INCLUDING the SN76489 writes,
simulated in py65: for AKL and AKY that is the replay plus the whole AY->SN
conversion, and for VGC and VGI it is the decode plus its writes. A call is
a frame of music, so a 25 Hz song is called half as often as a 50 Hz one -
the numbers are per call, not per field.

    python tools/compare_formats.py                 # the four demo tunes
    python tools/compare_formats.py path/to/song.sks

Writes build/formats.md. Needs beebasm, py65, numpy, an Arkos install, and
the vgm-player-bbc and vgm-packer repos beside this one; anything missing is
reported as a gap in the table rather than guessed at.
"""
import argparse
import os
import re
import subprocess
import sys

import numpy as np
from py65.devices.mpu6502 import MPU
from py65.memory import ObservableMemory

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(ROOT, 'build', 'fmt')
BEEB = os.path.dirname(os.path.dirname(ROOT))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'verify'))
import arkos                                                     # noqa: E402
import akl_reference                                             # noqa: E402

VGM_PLAYER = os.path.join(BEEB, 'Repos', 'vgm-player-bbc')
VGM_PACKER = os.path.join(BEEB, 'Repos', 'vgm-packer')
YM2SN = os.path.join(BEEB, 'Repos', 'nova-invite', 'bin', 'ym2sn.py')

LOAD = 0x1100
RET = 0x9000

FORMATS = ('akl', 'aky', 'akm', 'akg', 'vgc', 'vgi', 'vgm')

# The four discs example/build.py makes, in the order the README lists them.
TUNES = [
    ('Rhino - Acid Demo 21', os.path.join(ROOT, 'songs', 'Acid_demo_21.aks')),
    ('Targhan - Dead On Time', os.path.join(arkos.AT3, 'songs', 'STarKos',
     'Targhan - Dead On Time - Ingame.sks')),
    ('Tom&Jerry - Edge Grinder', os.path.join(
     BEEB, 'Repos', 'edge-beeb', 'source_cpc', 'Music', 'EDGEA.SKS')),
    ('Targhan - Orion Prime L4', os.path.join(arkos.AT3, 'songs', 'STarKos',
     'Targhan - Orion Prime - Level 4 - Theme 1.sks')),
]


def beebasm():
    for c in (os.path.join(ROOT, 'bin', 'beebasm.exe'),
              os.path.join(BEEB, 'Bin', 'beebasm.exe')):
        if os.path.exists(c):
            return c
    return 'beebasm'


def size_or_none(path):
    return os.path.getsize(path) if path and os.path.exists(path) else None


# ------------------------------------------------------------ the exports ---
def export_arkos(song, fmt, out):
    """AKL through this repo's exporter; the rest through Arkos's own."""
    if fmt == 'akl':
        r = subprocess.run([sys.executable, os.path.join(HERE, 'export_akl.py'),
                            song, '--addr', '0x3000', '-o', out],
                           cwd=ROOT, capture_output=True, text=True)
        return out if r.returncode == 0 and os.path.exists(out) else None
    if fmt == 'aky':
        exe = os.path.join(arkos.AT3, 'tools', 'SongToAky.exe')
        args = [exe, '-s', '1', '-bin', '-adr', '0x3000', song, out]
    else:
        exe = os.path.join(arkos.AT3, 'tools', 'SongTo%s.exe' % fmt.capitalize())
        args = [exe, '-bin', '-adr', '0x3000', song, out]
    if not os.path.exists(exe):
        return None
    r = subprocess.run(args, capture_output=True, text=True)
    return out if r.returncode == 0 and os.path.exists(out) else None


def export_vgm(song, stem):
    """SongToYm -> ym2sn.py -> .vgm, then the two packers."""
    exe = arkos.song_to_ym_exe()
    if not exe or not os.path.exists(YM2SN):
        return None, None, None
    ym = os.path.join(BUILD, stem + '.ym')
    if not os.path.exists(ym):
        r = subprocess.run([exe, '-p', '1', song, ym], capture_output=True, text=True)
        if r.returncode != 0:
            return None, None, None
    vgm = os.path.join(BUILD, stem + '.vgm')
    r = subprocess.run([sys.executable, YM2SN, ym, '-o', vgm],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(vgm):
        return None, None, None
    vgc = os.path.join(BUILD, stem + '.vgc')
    vgi = os.path.join(BUILD, stem + '.vgi')
    subprocess.run([sys.executable, os.path.join(VGM_PACKER, 'vgmpacker.py'),
                    vgm, '-o', vgc], capture_output=True, text=True)
    subprocess.run([sys.executable, os.path.join(VGM_PACKER, 'vgipacker.py'),
                    vgm, '-o', vgi], capture_output=True, text=True)
    return vgm, (vgc if os.path.exists(vgc) else None), \
        (vgi if os.path.exists(vgi) else None)


# -------------------------------------------------------- the measurements ---
def akl_plays(path, addr=0x3000, frames=4000):
    """Will this AKL export actually play?

    AT2's exporter can emit data whose own pointers run outside it - it does
    for Rhino's tune, which is why the AKL disc uses a different one
    (docs/format-akl.md). Fed that, the 6502 replay does not fail: it SPINS,
    and py65 spins with it, which is an hour of nothing rather than an
    error. akl_reference.py raises on the same data in milliseconds - at
    frame 414 for Rhino's tune, so ask over a good few thousand - and that
    is the only cheap way to know before the simulator is involved.
    """
    try:
        ref = akl_reference.Player(open(path, 'rb').read(), addr)
        for _ in range(frames):
            ref.play()
        return True
    except Exception:
        return False


def player_cost(song, player, limit=1800):
    """verify.py already builds, simulates and reports. Parse it.

    With a timeout, because AT2's AKL exporter can emit data its own format
    cannot play (docs/format-akl.md) and the harness does not always fail
    fast on it. A tune that times out is a gap in the table, not a stall.
    """
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, 'verify', 'verify.py'),
                            '--player', player, '--song', song, '--bass', '2'],
                           cwd=ROOT, capture_output=True, text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        print('    %s: verify.py timed out after %ds' % (player.upper(), limit))
        return None
    m = re.search(r'per 50 Hz field:\s+min (\d+)\s+mean (\d+)\s+p99 (\d+)\s+max (\d+)',
                  r.stdout)
    if not m:
        return None
    c = re.search(r'code:\s+(\d+) bytes', r.stdout)
    n = re.search(r'(\d+) calls', r.stdout)
    return dict(mean=int(m.group(2)), max=int(m.group(4)),
                code=int(c.group(1)) if c else 0, work=0,
                frames=int(n.group(1)) if n else None)


SIM = """\\ Generated by tools/compare_formats.py - do not edit, do not commit.
.zp_start
ORG &70
GUARD &9f
%(zp)s
.zp_end

ORG &1100
GUARD &7c00
.start
%(code)s

.vgm_buffer_start
ALIGN 256
.vgm_stream_buffers
  SKIP %(buf)d
.vgm_buffer_end
.vgm_data
INCBIN "%(data)s"
.end
SAVE "%(out)s", start, end, start
"""


def vgm_cost(data, kind):
    """Build vgm-player-bbc's player around this tune and time one call.

    The shape is test/vgi/measure.py's, over there: vgm_init with carry
    clear so the tune ends rather than loops, then vgm_update until it
    returns non-zero. The SN writes are inside the timing, as they are for
    AKL and AKY, so the two halves of the table are comparable.
    """
    lib = os.path.join(VGM_PLAYER, 'lib').replace('\\', '/')
    if kind == 'vgi':
        zp = 'INCLUDE "%s/vgiplayer.h.asm"' % lib
        code = 'INCLUDE "%s/vgiplayer.asm"' % lib
        buf = 11 * 256                          # 11 ring windows
    else:
        zp = ('INCLUDE "%s/vgcplayer_config.h.asm"\nINCLUDE "%s/vgcplayer.h.asm"'
              % (lib, lib))
        code = 'INCLUDE "%s/vgcplayer.asm"' % lib
        buf = 2048                              # 8 LZ4 windows
    out = os.path.join(BUILD, kind.upper())
    src = os.path.join(BUILD, 'sim_%s.asm' % kind)
    lbl = os.path.join(BUILD, 'labels_%s.txt' % kind)
    with open(src, 'w') as f:
        f.write(SIM % dict(zp=zp, code=code, buf=buf,
                           data=data.replace('\\', '/'),
                           out=out.replace('\\', '/')))
    cmd = [beebasm(), '-i', src]
    if kind == 'vgi':
        cmd += ['-D', 'VGI_UNROLL=0']
    cmd += ['-d', '-labels', lbl]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        sys.stderr.write(r.stdout + r.stderr)
        return None
    lab = eval(re.sub(r'(\d+)L', r'\1', open(lbl).read()))[0]
    img = open(out, 'rb').read()

    mem = ObservableMemory()
    for i, b in enumerate(img):
        mem[LOAD + i] = b
    mem.subscribe_to_write([0xFE4F], lambda a, v: None)
    mpu = MPU(memory=mem)

    def push():
        sp = mpu.sp
        mem[0x100 + sp] = ((RET - 1) >> 8) & 0xFF
        mem[0x100 + ((sp - 1) & 0xFF)] = (RET - 1) & 0xFF
        mpu.sp = (sp - 2) & 0xFF

    d = lab['vgm_data']
    mpu.a, mpu.x, mpu.y = lab['vgm_stream_buffers'] >> 8, d & 0xFF, (d >> 8) & 0xFF
    mpu.p &= ~1
    push()
    mpu.pc = lab['vgm_init']
    while mpu.pc != RET:
        mpu.step()

    per = []
    for _ in range(100000):
        push()
        mpu.pc = lab['vgm_update']
        mpu.a = 0
        c0 = mpu.processorCycles
        while mpu.pc != RET:
            mpu.step()
        if mpu.a != 0:                          # the terminating call
            break
        per.append(mpu.processorCycles - c0)
    a = np.array(per)
    return dict(mean=int(a.mean()), max=int(a.max()),
                code=lab['vgm_buffer_start'] - lab['start'],
                work=lab['vgm_buffer_end'] - lab['vgm_buffer_start'],
                frames=len(per))


# ------------------------------------------------------------------- main ---
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('songs', nargs='*')
    args = ap.parse_args()
    os.makedirs(BUILD, exist_ok=True)
    tunes = ([(os.path.splitext(os.path.basename(s))[0], s) for s in args.songs]
             or TUNES)

    rows = []
    bad_akl = set()
    for name, song in tunes:
        if not os.path.exists(song):
            print('skipping %s: not found' % name)
            continue
        stem = re.sub(r'\W+', '_', name)
        rate = arkos.replay_rate(song)
        print('\n%s  (%d Hz)' % (name, rate))

        sizes = {}
        for fmt in ('akl', 'aky', 'akm', 'akg'):
            sizes[fmt] = size_or_none(
                export_arkos(song, fmt, os.path.join(BUILD, '%s.%s' % (stem, fmt))))
        vgm, vgc, vgi = export_vgm(song, stem)
        sizes['vgm'] = size_or_none(vgm)
        sizes['vgc'] = size_or_none(vgc)
        sizes['vgi'] = size_or_none(vgi)

        akl_ok = bool(sizes['akl']) and akl_plays(
            os.path.join(BUILD, '%s.akl' % stem))
        if sizes['akl'] and not akl_ok:
            print('    AKL: exported %d bytes that will not play' % sizes['akl'])
            bad_akl.add((name, 'akl'))

        cost = {}
        for player in ('akl', 'aky', 'akm'):
            if not sizes[player] or (player == 'akl' and not akl_ok):
                continue
            c = player_cost(song, player)
            if c is None:
                bad_akl.add((name, player))
            else:
                cost[player] = c
        if os.path.isdir(VGM_PLAYER):
            if vgc:
                cost['vgc'] = vgm_cost(vgc, 'vgc')
            if vgi:
                cost['vgi'] = vgm_cost(vgi, 'vgi')

        frames = next((c['frames'] for c in cost.values()
                       if c and c.get('frames')), None)
        rows.append((name, rate, frames, sizes, cost))
        for f in FORMATS:
            c = cost.get(f)
            print('  %-4s %8s bytes  %s'
                  % (f.upper(), sizes[f] if sizes[f] else '-',
                     ('mean %5d  max %5d  code+work %5d'
                      % (c['mean'], c['max'], c['code'] + c['work'])) if c else ''))

    out = os.path.join(ROOT, 'build', 'formats.md')
    with open(out, 'w') as f:
        f.write('# What each format costs, over the four demo tunes\n\n')
        f.write('Generated by `tools/compare_formats.py`. Not committed.\n\n')
        f.write('Cycles are one player call including its SN76489 writes,\n')
        f.write('simulated in py65 at 2 MHz. AKM and AKG have no 6502 player\n')
        f.write('anywhere, so they are data sizes only.\n\n')
        for name, rate, frames, sizes, cost in rows:
            f.write('## %s (%d Hz%s)\n\n'
                    % (name, rate, ', %d calls' % frames if frames else ''))
            f.write('| format | tune bytes | player + workspace | mean | max |\n')
            f.write('|---|--:|--:|--:|--:|\n')
            for fmt in FORMATS:
                c = cost.get(fmt)
                f.write('| %s | %s | %s | %s | %s |\n'
                        % (fmt.upper(),
                           '{:,}'.format(sizes[fmt]) if sizes[fmt] else 'n/a',
                           '{:,}'.format(c['code'] + c['work']) if c else 'no player',
                           '{:,}'.format(c['mean']) if c else '-',
                           '{:,}'.format(c['max']) if c else '-'))
            f.write('\n')
    print('\n%s written' % out)


if __name__ == '__main__':
    main()
