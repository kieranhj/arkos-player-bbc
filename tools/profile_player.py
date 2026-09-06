#!/usr/bin/env python3
"""Where the cycles go: a per-routine and per-instruction profile of a player call.

verify.py already reports what a call COSTS. It does not say what it spends the
cycles ON, and every optimisation argument this repo has had so far was made
from reading the source. This runs the real lib/ sources in py65 - the same
image verify.py verifies - and attributes every cycle to the routine that
executed it, using beebasm's own label file.

Two views, because they answer different questions:

  1. by routine - inclusive (the routine and everything it calls) and exclusive
     (its own instructions only). Exclusive is what a rewrite of that routine
     can win; inclusive is what deleting the call can.
  2. by instruction - the hottest PCs, with the count and the cycles. This is
     where a redundant `lda` or a `jmp` that could be a fallthrough shows up,
     and it is per-address so a label is not needed to see it.

`--frames` matters: the whole tune is the honest number, but a few hundred
frames is enough to rank the routines and runs in seconds.

    python tools/profile_player.py --player akl --song "songs/EDGEA.SKS"
    python tools/profile_player.py --player akm --bass 2 --frames 2000

Run from the REPO ROOT. Needs the same things verify.py does, less the oracle:
this measures cost, not correctness, so it never needs Arkos installed.
"""

import argparse
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools', 'verify'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from py65.devices.mpu6502 import MPU                            # noqa: E402
from py65.memory import ObservableMemory                        # noqa: E402

import arkos                                                    # noqa: E402
import verify                                                   # noqa: E402


def build_dd(song, player, env_base, fixed=-1):
    """verify.build(), but with -dd: the LOCAL labels too.

    verify.py only needs the API symbols, so it dumps globals. A profile of
    ay2sn with globals only says "894 cycles somewhere in a 400-byte block",
    which is not an answer - every branch target inside a BeebASM `{}` block
    is local, and those are exactly the blocks worth attributing.
    """
    import re
    import subprocess
    path, size = verify.export_song(song, player, verify.SIM_SONG)
    labels = os.path.join(verify.BUILD, 'labels_dd.txt')
    subprocess.run([verify.beebasm(), '-i', 'tools/verify/sim.asm',
                    '-D', 'SIM_SONG=%d' % verify.SIM_SONG,
                    '-D', 'PLAYER_AKY=%d' % (player == 'aky'),
                    '-D', 'PLAYER_AKM=%d' % (player == 'akm'),
                    '-D', 'ENV_BASE=%d' % env_base,
                    '-D', 'BASS_MODE=%d' % fixed,
                    '-dd', '-labels', labels],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    lab = eval(re.sub(r'(\d+)L', r'\1', open(labels).read()))[0]
    lab = {n.lstrip('.'): a for n, a in lab.items()}
    img = open(os.path.join(verify.BUILD, 'Sim'), 'rb').read()
    return img, lab, path, size


# Absolute and absolute-indexed opcodes whose zero-page form is cheaper, and
# what each execution would save. `lda abs,x` and `lda zp,x` both cost 4 - the
# saving there is only the page-crossing penalty, which is why it is counted
# separately and measured rather than assumed.
ABS_TO_ZP = {
    # opcode: (mnemonic, mode, cycles saved by the zero-page form)
    0xAD: ('lda', 'abs', 1), 0xAE: ('ldx', 'abs', 1), 0xAC: ('ldy', 'abs', 1),
    0x8D: ('sta', 'abs', 1), 0x8E: ('stx', 'abs', 1), 0x8C: ('sty', 'abs', 1),
    0xCD: ('cmp', 'abs', 1), 0xEC: ('cpx', 'abs', 1), 0xCC: ('cpy', 'abs', 1),
    0x6D: ('adc', 'abs', 1), 0xED: ('sbc', 'abs', 1), 0x2D: ('and', 'abs', 1),
    0x0D: ('ora', 'abs', 1), 0x4D: ('eor', 'abs', 1), 0x2C: ('bit', 'abs', 1),
    0xEE: ('inc', 'abs', 1), 0xCE: ('dec', 'abs', 1), 0x4E: ('lsr', 'abs', 1),
    0x0E: ('asl', 'abs', 1), 0x6E: ('ror', 'abs', 1), 0x2E: ('rol', 'abs', 1),
    0x9D: ('sta', 'abs,x', 1),          # sta zp,x is 4, sta abs,x is 5
    0xBD: ('lda', 'abs,x', 0),          # both 4 - page crossing only
    0xB9: ('lda', 'abs,y', 0),          # zp,y exists for ldx only; see below
    0xBE: ('ldx', 'abs,y', 0),
}


def zp_census(pc_n, mem, lo, hi, own):
    """What zero page would be worth, per addressing mode, measured.

    "Trade RAM for cycles" on a 6502 usually means "move it to zero page",
    and the honest answer is not uniform: `sta abs,x` really is a cycle
    dearer than `sta zp,x`, `lda abs,x` is not - it is only dearer when the
    index carries into the next page. So this counts executions by mode AND
    counts the page crossings that actually happened, rather than assuming.
    """
    out = collections.Counter()
    cross = collections.Counter()
    for pc, n in pc_n.items():
        if not lo <= pc < hi:
            continue
        op = mem[pc]
        if op not in ABS_TO_ZP:
            continue
        mnem, mode, save = ABS_TO_ZP[op]
        out[(mnem, mode, save)] += n
        if mode in ('abs,x', 'abs,y'):
            base = mem[pc + 1] | (mem[pc + 2] << 8)
            # the operand is a 3-byte per-channel array, so a crossing shows
            # up whenever the base's page differs from base+2's
            if (base & 0xFF00) != ((base + 2) & 0xFF00):
                cross[(mnem, mode)] += n
    return out, cross


def sn_redundant_bytes(stream, state):
    """How many of these bytes a write-through cache could have elided.

    The SN76489's registers LATCH, so writing a tone or volume byte the
    register already holds is audibly nothing and costs 38 cycles. The one
    register that is not idempotent is the noise control: writing it resets
    the LFSR, which is a click, and ay2sn already dedupes it for that reason.

    A tone write is a PAIR - a latch byte carrying the low nibble and a data
    byte carrying the top six bits - so it is redundant only when the whole
    ten-bit period is unchanged, and elides two bytes when it is. A volume or
    noise write is one byte on its own.
    """
    saved, i = 0, 0
    while i < len(stream):
        b = stream[i]
        if not b & 0x80:                    # a stray data byte: always needed
            i += 1
            continue
        reg = (b >> 4) & 7
        if reg in (0, 2, 4) and i + 1 < len(stream) and not stream[i + 1] & 0x80:
            val = (b & 15) | (stream[i + 1] << 4)
            if state.get(reg) == val:
                saved += 2
            state[reg] = val
            i += 2
        else:
            val = b & 15
            if reg != 6 and state.get(reg) == val:      # never dedupe noise
                saved += 1
            state[reg] = val
            i += 1
    return saved


def code_labels(lab, lo, hi):
    """Label -> address, for labels inside the assembled code, sorted."""
    # Several names can share an address (`start` is `ay2sn`; a block's first
    # local label is its entry). Keep one, and prefer the one that reads as
    # the routine rather than the harness's bookend.
    best = {}
    for n, a in lab.items():
        if not lo <= a < hi:
            continue
        rank = (n in ('start', 'all_end'), '.' in n, n)
        if a not in best or rank < best[a][0]:
            best[a] = (rank, n)
    # beebasm emits data labels too; they sort into place and simply collect
    # zero cycles, which is itself the check that they ARE data.
    return sorted((a, nm) for a, (_, nm) in best.items())


def owner_table(labels, lo, hi):
    """A byte-indexed address -> owning label map, so attribution is O(1)."""
    own = [None] * (hi - lo)
    for i, (addr, name) in enumerate(labels):
        end = labels[i + 1][0] if i + 1 < len(labels) else hi
        for a in range(addr, min(end, hi)):
            own[a - lo] = name
    return own


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--player', default='akl', choices=('akl', 'aky', 'akm'))
    ap.add_argument('--song', default=verify.DEFAULT_SONG)
    ap.add_argument('--frames', type=int, default=1000)
    ap.add_argument('--bass', type=int, default=2, choices=(0, 1, 2))
    ap.add_argument('--fixed', type=int, default=-1, choices=(-1, 0, 1, 2),
                    help='BASS_MODE: assemble one bass voice instead of all three')
    ap.add_argument('--top', type=int, default=25,
                    help='how many routines / instructions to list')
    args = ap.parse_args()

    if not os.path.exists(args.song):
        raise SystemExit('song not found: %s' % args.song)

    env_base = (arkos.envelope_base(args.song)
                if args.player in ('akl', 'akm') else 8)
    img, lab, songpath, songsize = build_dd(args.song, args.player, env_base,
                                            args.fixed)

    lo, hi = lab['start'], lab['all_end']
    labels = code_labels(lab, lo, hi)
    own = owner_table(labels, lo, hi)

    mem = ObservableMemory()
    for i, b in enumerate(img):
        mem[verify.LOAD + i] = b
    writes = []
    mem.subscribe_to_write([0xFE4F], lambda a, v: writes.append(v))
    mpu = MPU(memory=mem)
    RET = verify.RET

    def call(addr):
        sp = mpu.sp
        mem[0x100 + sp] = ((RET - 1) >> 8) & 0xFF
        mem[0x100 + ((sp - 1) & 0xFF)] = (RET - 1) & 0xFF
        mpu.sp = (sp - 2) & 0xFF
        mpu.pc = addr
        while mpu.pc != RET:
            mpu.step()

    mpu.a, mpu.x, mpu.y = verify.SIM_SONG & 0xFF, verify.SIM_SONG >> 8, 0
    call(lab['%s_init' % args.player])
    if args.fixed < 0:
        mem[lab['bass_mode']] = args.bass
    else:
        args.bass = args.fixed

    # ---- the profiled run -------------------------------------------------
    # Exclusive cycles are the instruction's own. Inclusive needs the call
    # stack, so JSR/RTS are tracked: a routine is "on the stack" between them
    # and every cycle spent while it is counts towards it, once - a recursive
    # or re-entered routine would double count, and none here is either.
    excl = collections.Counter()        # label -> cycles executed in its body
    calls = collections.Counter()       # label -> times entered via JSR
    incl = collections.Counter()        # label -> cycles with it on the stack
    pc_cyc = collections.Counter()      # address -> cycles
    pc_n = collections.Counter()        # address -> executions
    stack = []                          # labels currently entered
    frame_cost = []
    sn_state = {}                       # SN register -> the value it holds
    sn_bytes = sn_saved = 0

    frame = lab['music_frame']
    total = 0
    for f in range(args.frames):
        sp = mpu.sp
        mem[0x100 + sp] = ((RET - 1) >> 8) & 0xFF
        mem[0x100 + ((sp - 1) & 0xFF)] = (RET - 1) & 0xFF
        mpu.sp = (sp - 2) & 0xFF
        mpu.pc = frame
        c0 = mpu.processorCycles
        del stack[:]
        while mpu.pc != RET:
            pc = mpu.pc
            op = mem[pc]
            before = mpu.processorCycles
            mpu.step()
            n = mpu.processorCycles - before
            pc_cyc[pc] += n
            pc_n[pc] += 1
            if lo <= pc < hi:
                name = own[pc - lo]
                excl[name] += n
                for s in stack:
                    incl[s] += n
                if op == 0x20:                          # JSR
                    tgt = mpu.pc
                    tname = own[tgt - lo] if lo <= tgt < hi else None
                    if tname is not None:
                        calls[tname] += 1
                        stack.append(tname)
                elif op == 0x60 and stack:              # RTS
                    stack.pop()
        frame_cost.append(mpu.processorCycles - c0)
        total += frame_cost[-1]
        sn_bytes += len(writes)
        sn_saved += sn_redundant_bytes(writes, sn_state)
        del writes[:]

    n = len(frame_cost)
    print('song:   %s (%s, %d bytes)'
          % (os.path.relpath(args.song, ROOT), args.player.upper(), songsize))
    print('code:   %d bytes (&%04X-&%04X)  bass_mode %d'
          % (hi - lo, lo, hi, args.bass))
    print('frames: %d   mean %.0f  min %d  max %d cycles a call'
          % (n, total / float(n), min(frame_cost), max(frame_cost)))
    print()

    # The two halves of the library, which is the decision a host actually
    # faces: the replay is per-format, ay2sn is shared by all three, so a
    # cycle saved there is saved three times.
    spine = set()
    lo_a = min(a for a, nm in labels)
    for a, nm in labels:
        if a < lab['%s_init' % args.player] or nm.split('.')[0] in (
                'sn_write', 'bass_pick', 'bass_claim', 'bass_update',
                'bass_stop', 'bass_timer_off', 'bass_irq', 'div15',
                'akl_silence', 'chan_bit'):
            spine.add(nm)
    conv = sum(c for nm, c in excl.items() if nm in spine)
    print('SPLIT: ay2sn + the bass %7.0f cycles a call (%.0f%%)'
          % (conv / float(n), 100.0 * conv / total))
    print('       the %s replay      %7.0f cycles a call (%.0f%%)'
          % (args.player.upper(), (total - conv) / float(n),
             100.0 * (total - conv) / total))
    print()

    print('CYCLES BY ROUTINE, mean per call  (excl = its own instructions)')
    print('  %-22s %9s %9s %8s   %s'
          % ('routine', 'excl', 'incl', 'calls', 'share'))
    for name, c in excl.most_common(args.top):
        print('  %-22s %9.1f %9.1f %8.2f   %5.1f%%'
              % (name, c / float(n),
                 (incl[name] + c) / float(n) if name in incl else c / float(n),
                 calls[name] / float(n), 100.0 * c / total))
    print()

    print('CYCLES BY TOP-LEVEL ROUTINE (locals folded into their block)')
    grp = collections.Counter()
    for nm, c in excl.items():
        grp[nm.split('.')[0]] += c
    for nm, c in grp.most_common(args.top or 20):
        print('  %-22s %9.1f   %5.1f%%' % (nm, c / float(n), 100.0 * c / total))
    print()

    print('SN76489 WRITES: %.2f bytes a call, of which %.2f say nothing the'
          % (sn_bytes / float(n), sn_saved / float(n)))
    print('  chip did not already hold - %.0f%%, and worth ~%.0f cycles a call'
          % (100.0 * sn_saved / max(1, sn_bytes), 38.0 * sn_saved / n))
    print('  at 38 cycles a byte (jsr + sn_write).')
    print()

    # What the call structure itself costs. A jsr is 6 and its rts 6, so
    # every subroutine in the frame is 12 cycles before it does anything.
    # This is the honest size of the "inline it" prize - and note it is a
    # CEILING: inlining a routine called from three places costs three
    # copies of its body, which is why the number matters more than the idea.
    njsr = sum(c for pc, c in pc_n.items()
               if lo <= pc < hi and mem[pc] == 0x20)
    print('CALL OVERHEAD: %.1f jsr/rts pairs a call = %.0f cycles (%.1f%%),'
          % (njsr / float(n), 12.0 * njsr / n, 100.0 * 12.0 * njsr / total))
    print('  before any of them does any work. The ceiling on inlining.')
    print()

    cen, cross = zp_census(pc_n, mem, lo, hi, own)
    print('WHAT ZERO PAGE WOULD BE WORTH  (executions a call, and the cycles)')
    tot = 0.0
    for (mnem, mode, save), c in sorted(cen.items(), key=lambda kv: -kv[1]):
        gain = save * c / float(n)
        tot += gain
        note = ''
        if mode in ('abs,x', 'abs,y'):
            xc = cross.get((mnem, mode), 0) / float(n)
            note = '  (%.2f a call cross a page: +%.1f cycles)' % (xc, xc)
            tot += xc if save == 0 else 0
        print('  %-4s %-6s %8.2f a call  %6.1f cycles%s'
              % (mnem, mode, c / float(n), gain, note))
    print('  %-11s %8s              %6.1f cycles a call, %.1f%% of the total'
          % ('TOTAL', '', tot, 100.0 * tot * n / total))
    print()

    print('HOTTEST INSTRUCTIONS, mean cycles per call')
    print('  %-8s %-22s %9s %8s' % ('addr', 'in', 'cycles', 'exec'))
    for pc, c in pc_cyc.most_common(args.top):
        name = own[pc - lo] if lo <= pc < hi else '(outside)'
        off = pc - next(a for a, nm in labels if nm == name) if name != '(outside)' else 0
        print('  &%04X+%-3d %-22s %9.1f %8.2f'
              % (pc, off, name, c / float(n), pc_n[pc] / float(n)))


if __name__ == '__main__':
    main()
