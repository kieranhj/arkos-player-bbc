#!/usr/bin/env python3
"""Check akm_reference.py's decode against ARKOS'S OWN ANNOTATION of the data.

`SongToAkm.exe` without `-bin` writes the same song as assembler source with
a comment on every byte saying what it means:

    db 126    ; New instrument (2). New escaped note: 76. Primary wait (0).
    db 76     ;   Escape note value.
    db 2      ;   Escape instrument value.

That is Arkos stating, byte by byte, how the exporter intended the data to be
read - a far sharper oracle for the TRACK layer than a register log. A
register log only shows a decode fault once it has changed an audible
register, by which time the cause is hundreds of frames back; this shows it
on the cell that caused it.

The chain, and nothing is checked against itself:

  1. The source export is assembled here and compared to the BINARY export of
     the same song, byte for byte. If those disagree the tool refuses, rather
     than reporting against a mapping it has not proved.
  2. akm_reference.py replays the binary with its decode log switched on, and
     every cell it decodes - note, instrument, wait - is held against the
     comment at that address.

    python tools/verify/akm_source_check.py <song.aks|.sks> [--frames N]
    python tools/verify/akm_source_check.py --all        # the whole corpus

Needs an Arkos Tracker 3 install for SongToAkm.exe.
"""

import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import akm_reference                                             # noqa: E402
import arkos                                                     # noqa: E402

BASE = 0x4000

LABEL = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\s*$')
DIRECTIVE = re.compile(r'^\s+(db|dw)\s+([^;]*?)\s*(?:;(.*))?$', re.I)
WORD = re.compile(r'(?<![\w0-9])[A-Za-z_][A-Za-z0-9_]*')


# --------------------------------------------------------------- assembling --
def _value(expr, labels, here):
    """A label, a number, or arithmetic over them.

    Arkos emits `Foo - 2`, `0 * 2 + 1`, and for a track offset
    `((Track - ($ + 2)) & #ff00) / 256`. `#` is hex and `$` is the address of
    the byte being emitted - and note that those offset expressions are
    Arkos itself confirming that a track offset is measured from just PAST
    the two bytes that encode it.
    """
    e = re.sub(r'#([0-9A-Fa-f]+)', lambda m: str(int(m.group(1), 16)),
               expr.strip())
    e = e.replace('$', str(here))
    for n in set(WORD.findall(e)):
        if n not in labels:
            raise KeyError(n)
    e = WORD.sub(lambda m: str(labels[m.group(0)]), e)
    if not re.match(r'^[\d\s()+\-*/&|]+$', e):
        raise ValueError('cannot evaluate %r' % expr)
    return int(eval(e, {'__builtins__': {}}, {}))


def assemble(path, base=BASE):
    """(bytes, {addr: comment}) from a SongToAkm source export."""
    lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    labels, addr = {}, base
    for ln in lines:                                    # pass 1: sizes
        m = LABEL.match(ln)
        if m and not ln.startswith((' ', '\t')):
            labels[m.group(1)] = addr
            continue
        m = DIRECTIVE.match(ln)
        if m:
            addr += len(m.group(2).split(',')) * \
                (1 if m.group(1).lower() == 'db' else 2)
    out, comments, addr = bytearray(), {}, base
    for ln in lines:                                    # pass 2: emit
        m = DIRECTIVE.match(ln)
        if not m:
            continue
        kind, args, comment = m.group(1).lower(), m.group(2), (m.group(3) or '')
        for a in args.split(','):
            v = _value(a, labels, addr)
            if comment.strip():
                comments[addr] = comment.strip()
            if kind == 'db':
                out.append(v & 0xFF)
                addr += 1
            else:
                out += bytes((v & 0xFF, (v >> 8) & 0xFF))
                addr += 2
    return bytes(out), comments, labels


# ------------------------------------------------------ reading the comments --
NOTE_PATS = (('reference', r'Note reference \((\d+)\)'),
             ('new-escape', r'New escaped note: (\d+)'),
             ('same-escape', r'Same escaped note: (\d+)'))
INST_PATS = (('primary', r'Primary instrument \((\d+)\)'),
             ('secondary', r'Secondary instrument \((\d+)\)'),
             ('new-escape', r'New instrument \((\d+)\)'))
WAIT_PATS = (('primary', r'Primary wait \((\d+)\)'),
             ('secondary', r'Secondary wait \((\d+)\)'),
             ('new-escape', r'New wait \((\d+)\)'))


def parse_cell(t):
    """Arkos's cell comment -> what it claims. None if the line is not a cell."""
    got = {}
    if t.startswith('Effect only'):
        got['note_kind'] = None
    else:
        for kind, pat in NOTE_PATS:
            m = re.search(pat, t)
            if m:
                got['note_kind'], got['note'] = kind, int(m.group(1))
                break
        else:
            return None
        for kind, pat in INST_PATS:
            m = re.search(pat, t)
            if m:
                got['inst_kind'], got['inst'] = kind, int(m.group(1))
                break
        else:
            got['inst_kind'] = 'same-escape'    # rendered as nothing at all
    for kind, pat in WAIT_PATS:
        m = re.search(pat, t)
        if m:
            got['wait_kind'], got['wait'] = kind, int(m.group(1))
            break
    else:
        got['wait_kind'] = 'same-escape'        # likewise
    return got


EFFECT_PATS = (
    (0, r'Reset effect, with inverted volume: (\d+)'),
    (1, r'Volume effect, with inverted volume: (\d+)'),
    (2, r'Pitch (up|down): (\d+)'),
    (3, r'Arpeggio table effect (\d+)'),
    (4, r'Pitch table effect (\d+)'),
    (5, r'Force instrument speed effect (\d+)'),
    (6, r'Force arpeggio speed effect (\d+)'),
    (7, r'Force pitch(?: table)? speed effect (\d+)'),
)


def parse_effect(t):
    """Arkos's effect comment -> (number, value). None if not an effect."""
    for num, pat in EFFECT_PATS:
        m = re.search(pat, t)
        if m:
            if num == 2:
                # The comment gives the 16-bit magnitude and the DIRECTION,
                # which is the sign bit - so it also states which way round
                # Arkos means bit 15 to be read.
                return 2, (m.group(1), int(m.group(2)))
            return num, int(m.group(1))
    return None


# -------------------------------------------------------------------- driver --
def export(song, out_bin, out_src, exe):
    if subprocess.run([exe, '-s', '1', '-bin', '-adr', hex(BASE), song, out_bin],
                      capture_output=True).returncode:
        return False
    return not subprocess.run([exe, '-s', '1', song, out_src],
                              capture_output=True).returncode


def check(song, frames, exe):
    """((checked, skipped, disagreements), None) or (None, why-not)."""
    d = tempfile.mkdtemp()
    b, s = os.path.join(d, 's.akm'), os.path.join(d, 's.asm')
    try:
        if not export(song, b, s, exe):
            return None, 'export failed'
        binary = open(b, 'rb').read()
        try:
            asm, comments, labels = assemble(s, BASE)
        except (KeyError, ValueError) as e:
            return None, 'cannot assemble the source export: %s' % e
        if asm != binary:
            n = min(len(asm), len(binary))
            at = next((i for i in range(n) if asm[i] != binary[i]), n)
            return None, ('source and binary exports disagree at +%d (%d vs %d '
                          'bytes) - this tool is wrong, not the player'
                          % (at, len(asm), len(binary)))

        p = akm_reference.Player(binary, BASE)
        p.trace = []
        try:
            for _ in range(frames):
                p.play()
        except akm_reference.AkmDataError as e:
            return None, 'data fault: %s' % e

        bad, checked, skipped, seen = [], 0, 0, set()

        # ---- the linker: are we reading the tracks Arkos names? ----
        # The cell checks below cannot see this. A wrong track pointer still
        # reads perfectly valid cells - just the wrong ones, at the wrong
        # time - so every cell would agree with its comment and the tune
        # would still be wrong. This is the check for that.
        lnk_checked, lnk_seen = 0, set()
        for e in p.lnk_trace:
            if e['at'] in lnk_seen:
                continue
            lnk_seen.add(e['at'])
            for a in range(e['at'], e['end']):
                c = comments.get(a)
                if not c:
                    continue
                m = re.search(r'New track \((\d+)\) for channel (\d+)', c)
                if m:
                    lnk_checked += 1
                    want = labels.get('Subsong0_Track%s' % m.group(1))
                    ch = int(m.group(2)) - 1
                    if want is not None and e['tracks'][ch] != want:
                        bad.append((a, 'track pointer for channel %d' % (ch + 1),
                                    '&%04X' % e['tracks'][ch],
                                    '&%04X (Track%s)' % (want, m.group(1)), c))
                    continue
                m = re.search(r'New height', c)
                if m:
                    lnk_checked += 1
                    if e['height'] != p.b(a):
                        bad.append((a, 'pattern height', e['height'],
                                    p.b(a), c))
                    continue
                m = re.search(r'New speed', c)
                if m:
                    lnk_checked += 1
                    if e['speed'] != p.b(a):
                        bad.append((a, 'speed', e['speed'], p.b(a), c))

        inst_checked, inst_seen = 0, set()
        for e in p.inst_trace:
            at = e['at']
            if at in inst_seen:
                continue
            inst_seen.add(at)
            c = comments.get(at)
            if not c:
                continue
            m = re.match(r'^Volume: (\d+)\.', c)
            if not m:
                continue
            inst_checked += 1
            if e['vol'] is None:
                bad.append((at, 'instrument volume', 'hardware', m.group(1), c))
            elif e['vol'] != int(m.group(1)):
                bad.append((at, 'instrument volume', e['vol'],
                            int(m.group(1)), c))
        fx_checked, fx_seen = 0, set()
        for e in p.fx_trace:
            at = e['at']
            if at in fx_seen:
                continue
            fx_seen.add(at)
            c = comments.get(at)
            want = parse_effect(c) if c else None
            if want is None:
                continue
            fx_checked += 1
            num, val = want
            if e['num'] != num:
                bad.append((at, 'effect number', e['num'], num, c))
                continue
            if num in (0, 1):
                if e['inv_vol'] != val:
                    bad.append((at, 'inverted volume', e['inv_vol'], val, c))
            elif num == 2:
                sign, mag = val
                # Arkos renders a STOP as "Pitch down: 0" - the data nibble's
                # bit 0 is clear and no speed bytes follow. Checked against
                # the source export: `db 4 ; Pitch down: 0.` is followed by
                # the next cell, not by a Pitch LSB/MSB pair.
                if mag == 0:
                    if e['pud']:
                        bad.append((at, 'pitch up/down', 'started', 'stopped', c))
                elif not e['pud']:
                    bad.append((at, 'pitch up/down', 'stopped', 'started', c))
                else:
                    sp = e['speed']
                    ours = (sp & 0x7FFF, 'up' if sp & 0x8000 else 'down')
                    if ours != (mag, sign):
                        bad.append((at, 'pitch speed', '%d %s' % ours,
                                    '%d %s' % (mag, sign), c))
            elif num == 3 and e['arp'] != val:
                bad.append((at, 'arpeggio table', e['arp'], val, c))
            elif num == 4 and e['pit'] != val:
                bad.append((at, 'pitch table', e['pit'], val, c))
            elif num == 5 and e['inst_speed'] != val:
                bad.append((at, 'instrument speed', e['inst_speed'], val, c))
            elif num == 6 and e['arp_speed'] != val:
                bad.append((at, 'arpeggio speed', e['arp_speed'], val, c))
            elif num == 7 and e['pit_speed'] != val:
                bad.append((at, 'pitch speed', e['pit_speed'], val, c))

        for e in p.trace:
            at = e['at']
            if at in seen:              # tracks loop; check each cell once
                continue
            seen.add(at)
            c = comments.get(at)
            want = parse_cell(c) if c else None
            if want is None:
                skipped += 1
                continue
            checked += 1

            def fail(what, ours, theirs, _at=at, _c=c):
                bad.append((_at, what, ours, theirs, _c))

            if 'wait' in want and want['wait'] != e['wait']:
                fail('wait', e['wait'], want['wait'])
            if want['note_kind'] is None:
                if e['note'] is not None:
                    fail('note', e['note'], 'none (effect only)')
                continue
            if want['note_kind'] == 'reference':
                ref = p.b(p.note_tbl + want['note'])
                if e['note'] != ref:
                    fail('note (reference %d)' % want['note'], e['note'], ref)
            elif e['note'] != want['note']:
                fail('note (%s)' % want['note_kind'], e['note'], want['note'])
            if 'inst' in want and e['inst'] != want['inst']:
                fail('instrument (%s)' % want['inst_kind'],
                     e['inst'], want['inst'])
        return (checked + fx_checked + inst_checked + lnk_checked,
                skipped, bad), None
    finally:
        for f in (b, s):
            try:
                os.remove(f)
            except OSError:
                pass
        try:
            os.rmdir(d)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('song', nargs='?')
    ap.add_argument('--all', action='store_true', help='the whole corpus')
    ap.add_argument('--frames', type=int, default=4000)
    ap.add_argument('--exporter',
                    default=os.path.join(arkos.AT3, 'tools', 'SongToAkm.exe'))
    args = ap.parse_args()

    if not os.path.exists(args.exporter):
        raise SystemExit('SongToAkm.exe not found at %s' % args.exporter)

    if args.all:
        songs = []
        for d in ('songs/STarKos', 'songs/ArkosTracker2', 'songs/ArkosTracker3'):
            songs += sorted(glob.glob(os.path.join(arkos.AT3, d, '*.sks')) +
                            glob.glob(os.path.join(arkos.AT3, d, '*.aks')))
        songs += sorted(glob.glob(os.path.join(ROOT, 'songs', '*.aks')))
    elif args.song:
        songs = [args.song]
    else:
        raise SystemExit('give a song, or --all')

    tot_bad = tot_ok = tot_songs = clean = 0
    for s in songs:
        got, err = check(s, args.frames, args.exporter)
        nm = os.path.basename(s)[:46]
        if err:
            print('%-46s -- %s' % (nm, err))
            continue
        checked, skipped, bad = got
        tot_songs += 1
        tot_ok += checked
        tot_bad += len(bad)
        if bad:
            print('%-46s %5d cells, *** %d DISAGREE ***' % (nm, checked, len(bad)))
            for at, what, ours, theirs, c in bad[:3]:
                print('    &%04X %s: ours %s, Arkos %s' % (at, what, ours, theirs))
                print('          %s' % c)
        else:
            clean += 1
            print('%-46s %5d cells, all agree' % (nm, checked))
    print("\n%d songs, %d cells checked against Arkos's own annotation, "
          "%d disagree" % (tot_songs, tot_ok, tot_bad))
    if tot_songs:
        print('%d of %d songs decode exactly as Arkos says they should'
              % (clean, tot_songs))
    return 1 if tot_bad else 0


if __name__ == '__main__':
    sys.exit(main())
