"""Reference AKM ("minimalist") player: a transcription of Arkos Tracker 3's
PlayerAkm.asm (Z80) into Python, producing the 14 AY registers a frame.

Written to prove the format is understood BEFORE any 6502 is written, exactly
as akl_reference.py was. It is checked against the register log SongToYm.exe
produces from the same song with Arkos's own full player - an oracle outside
this project entirely.

The Z80 is not transcribable directly: it uses `ld sp,` as a data pointer to
push the PSG registers out through a RET table, and it self-modifies its own
instruction operands to hold every value read from the song header. This is a
rewrite that reproduces its ARITHMETIC, statement for statement, and nothing
of its mechanism.

Five things in here read as bugs and are not. Each is Arkos's behaviour and
each is marked FAITHFUL at the point it happens.
"""

# PLY_AKM_PeriodTable, the 1 MHz CPC branch (PLY_AKM_HARDWARE_CPC). Twelve
# entries, octave 0; every other octave is derived by shifting.
OCTAVE0 = [3822, 3608, 3405, 3214, 3034, 2863,
           2703, 2551, 2408, 2273, 2145, 2025]


def _build_periods():
    """PLY_AKM_CalculatePeriodForBaseNote's octave search, for all 256 notes.

    The note index is 8-bit and wraps: it is base note + instrument arpeggio +
    arpeggio table value, added without any mask, so every value 0-255 has to
    mean something. Above note ~110 the shifts take the period to zero, which
    is what Arkos's player does too.

    NOTE THIS IS NOT lib/akl_periods.asm's TABLE. AKL ships a precomputed
    128-note table; AKM derives its periods at run time by halving, rounding
    on the last bit shifted out. The two disagree on six notes - 18, 21, 23,
    28, 49 and 56, each by one - so the AKL table CANNOT be reused here.
    Measured 2026-09-05; see docs/format-akm.md.
    """
    out = []
    for n in range(256):
        a, octave = n, 0
        while a >= 12:                  # inc b / sub c / jr nc
            a -= 12
            octave += 1
        p, carry = OCTAVE0[a], 0
        for _ in range(octave):
            carry = p & 1               # srl h / rr l
            p >>= 1
        if octave and carry:            # jr nc / inc hl - round up
            p += 1
        out.append(p & 0xFFFF)
    return out


PERIODS = _build_periods()


ENV_BASE = 8      # the format's own shapes; see lib/akmplayer.asm.
                  # EDGEA needs 12. THIS MUST MATCH THE PLAYER'S.


class AkmDataError(Exception):
    """The AKM stream references data outside itself - an export fault."""


def s8(v):
    return v - 256 if v & 0x80 else v


def sra(v):
    """The Z80's SRA: arithmetic shift right, sign preserved."""
    return s8(v) >> 1


FIELDS = (
    'wait transp base_note esc_note esc_inst esc_wait '
    'pt_track pt_start_track pt_inst inst_step inst_speed inv_vol '
    'pud_used pitch_dec pitch_int pitch_speed '
    'arp_used pt_arp arp_off arp_step arp_speed arp_orig_speed arp_val '
    'pit_used pt_pit pit_off pit_step pit_speed pit_orig_speed pit_val'
).split()


class Track(object):
    __slots__ = FIELDS

    def __init__(self):
        for f in FIELDS:
            setattr(self, f, 0)


class Player(object):
    def __init__(self, data, base, subsong=0):
        self.d = data
        self.base = base
        self.stats = {}

        # ---- song header ----
        self.pt_inst_tbl = self.w(base + 0)
        self.pt_arp_tbl = self.w(base + 2)      # already biased by -2
        self.pt_pit_tbl = self.w(base + 4)      # (entry 0 is not encoded)
        ss = self.w(base + 6 + subsong * 2)

        # ---- subsong header, in PLY_AKM_InitVars_Start's order ----
        self.note_tbl = self.w(ss + 0)
        self.track_idx = self.w(ss + 2)
        self.speed = self.b(ss + 4)
        self.prim_inst = self.b(ss + 5)
        self.sec_inst = self.b(ss + 6)
        self.prim_wait = self.b(ss + 7)
        self.sec_wait = self.b(ss + 8)
        self.def_note = self.b(ss + 9)
        self.def_inst = self.b(ss + 10)
        self.def_wait = self.b(ss + 11)
        self.note_and_fx_flag = self.b(ss + 12)
        self.linker = ss + 13

        self.pat_height = 0
        self.prev_height = 0
        self.tick = (self.speed - 1) & 0xFF
        self.fx_flag = 0
        self.tr = [Track(), Track(), Track()]

        # Every channel starts on instrument 0 - the empty one - past its
        # speed byte, so that a song not opening with an instrument on all
        # three channels still has something to read.
        p = self.w(self.pt_inst_tbl) + 1
        for t in self.tr:
            t.pt_inst = p

        # Optional decode log, for tools/verify/akm_source_check.py. None
        # switches it off entirely and costs nothing.
        self.trace = None
        self.fx_trace = []
        self.inst_trace = []
        self.lnk_trace = []
        self._cell_at = self._cell_note = self._cell_inst = None

        self.regs = [0] * 14
        self.r13 = 0
        self.r13_old = 0
        self.r13_sent = None
        self.loops = 0

    # ---- memory -----------------------------------------------------------
    def b(self, a):
        o = a - self.base
        if not 0 <= o < len(self.d):
            raise AkmDataError(
                'read of &%04X, outside the song (&%04X-&%04X). The exported '
                'data is asking for something it does not contain.'
                % (a, self.base, self.base + len(self.d) - 1))
        return self.d[o]

    def w(self, a):
        return self.b(a) | (self.b(a + 1) << 8)

    def note(self, k):
        self.stats[k] = self.stats.get(k, 0) + 1

    # ---- linker -----------------------------------------------------------
    def read_linker(self):
        hl = self.linker
        while True:                                     # PLY_AKM_LinkerPostPt
            for t in self.tr:
                t.wait = 0
                t.esc_note = self.def_note
                t.esc_inst = self.def_inst
                t.esc_wait = self.def_wait

            start = hl
            flags = self.b(hl)
            hl += 1

            # The flags byte is consumed by eight `rr b` in total - one for
            # the speed bit, one for the height bit, then two per channel -
            # so the carry rotated in at bit 7 never reaches bit 0. FAITHFUL:
            # this is why the Z80 can leave the incoming carry undefined.
            speed_change, flags = flags & 1, flags >> 1
            if speed_change:
                a = self.b(hl)
                hl += 1
                if a == 0:                              # end of song
                    hl = self.w(hl)
                    self.loops += 1
                    continue                            # re-run PostPt
                self.speed = a
                self.note('linker:speed')

            height_change, flags = flags & 1, flags >> 1
            if height_change:
                self.prev_height = self.b(hl)
                hl += 1
            self.pat_height = self.prev_height

            for t in self.tr:
                hl, flags = self.transposition_and_track(t, hl, flags)

            if self.trace is not None:
                self.lnk_trace.append(
                    {'at': start, 'end': hl, 'speed': self.speed,
                     'height': self.pat_height,
                     'tracks': [t.pt_track for t in self.tr],
                     'transp': [t.transp for t in self.tr]})
            self.linker = hl
            return

    def transposition_and_track(self, t, hl, flags):
        transp, flags = flags & 1, flags >> 1
        if transp:
            t.transp = self.b(hl)
            hl += 1
            self.note('linker:transposition')

        new_track, flags = flags & 1, flags >> 1
        if not new_track:
            # No new track: rewind to the start of the one already playing.
            t.pt_track = t.pt_start_track
            return hl, flags

        a = self.b(hl)
        hl += 1
        if a & 0x80:                                    # sla a -> carry
            # A reference: the low seven bits are the index, and the shift
            # has already made it index * 2.
            idx = (a << 1) & 0xFF
            addr = self.w(self.track_idx + idx)
            self.note('linker:track-reference')
        else:
            # An offset from just past the two bytes that encode it.
            lo = self.b(hl)
            hl += 1
            addr = (hl + ((a << 8) | lo)) & 0xFFFF
            self.note('linker:track-offset')
        t.pt_start_track = t.pt_track = addr
        return hl, flags

    # ---- track ------------------------------------------------------------
    def read_track(self, t):
        if t.wait:
            t.wait -= 1
            return
        hl = t.pt_track

        note = None
        self._cell_at = hl
        self._cell_note = self._cell_inst = None
        while True:                                     # RT_GetDataByte
            bb = self.b(hl)
            self._cell_at = hl
            hl += 1
            a = bb & 0x0F

            if a < self.note_and_fx_flag:               # 0-11, or 0-12
                note = self.b(self.note_tbl + a)
                break
            if a == 12:
                # "Note and effects": the whole cell is re-encoded in the
                # NEXT byte, and this one exists only to raise the flag.
                # Reached only when the song has effects at all; when it has
                # not, the header's flag is 13 and 12 is a note reference.
                self.note('cell:note-and-effects')
                self.fx_flag = 1
                continue
            if a == 13:                                 # empty note
                if bb & 0x10:
                    self.fx_flag = 1
                    self.note('cell:effects-only')
                return self.read_wait_and_effects(t, bb, hl)
            if a == 14:
                self.note('cell:new-escape-note')
                note = self.b(hl)
                hl += 1
                t.esc_note = note
            else:                                       # 15
                self.note('cell:same-escape-note')
                note = t.esc_note
            break

        t.base_note = (note + t.transp) & 0xFF
        self._cell_note = note

        # ---- instrument ----
        ii = bb & 0x30
        if ii == 0x00:
            inst = t.esc_inst
        elif ii == 0x10:
            inst = self.prim_inst
        elif ii == 0x20:
            inst = self.sec_inst
        else:
            inst = self.b(hl)
            hl += 1
            t.esc_inst = inst
            self.note('cell:new-escape-instrument')

        self._cell_inst = inst
        p = self.w(self.pt_inst_tbl + ((inst * 2) & 0xFF))
        t.inst_speed = self.b(p)
        t.pt_inst = p + 1
        t.inst_step = 0

        # A new instrument resets the track pitch and both table offsets -
        # but NOT the pitch's decimal part, which the Z80 leaves alone with
        # a comment saying the difference should not be noticeable.
        t.pud_used = 0
        t.pitch_int = 0
        t.arp_off = 0
        t.arp_step = 0
        t.arp_speed = t.arp_orig_speed
        t.pit_off = 0
        t.pit_step = 0
        t.pit_speed = t.pit_orig_speed

        return self.read_wait_and_effects(t, bb, hl)

    def read_wait_and_effects(self, t, bb, hl):
        ww = bb & 0xC0
        if ww == 0x00:
            wait = t.esc_wait
        elif ww == 0x40:
            wait = self.prim_wait
        elif ww == 0x80:
            wait = self.sec_wait
        else:
            wait = self.b(hl)
            hl += 1
            t.esc_wait = wait
            self.note('cell:new-escape-wait')
        t.wait = wait
        if self.trace is not None:
            self.trace.append({'at': self._cell_at, 'note': self._cell_note,
                               'inst': self._cell_inst, 'wait': wait,
                               'transp': t.transp})

        if self.fx_flag:
            self.fx_flag = 0
            hl = self.read_effects(t, hl)
        t.pt_track = hl

    # ---- effects ----------------------------------------------------------
    def read_effects(self, t, hl):
        while True:
            bb = self.b(hl)
            at = hl
            hl += 1
            num = (bb >> 1) & 7
            a = (bb >> 4) & 0x0F
            self.note('fx%d' % num)
            hl = self.FX[num](self, t, a, hl)
            if self.trace is not None:
                self.fx_trace.append({'at': at, 'num': num, 'data': a,
                                      'inv_vol': t.inv_vol,
                                      'pud': t.pud_used,
                                      'speed': t.pitch_speed,
                                      'arp': t.arp_used, 'pit': t.pit_used,
                                      'inst_speed': t.inst_speed,
                                      'arp_speed': t.arp_speed,
                                      'pit_speed': t.pit_speed})
            if not (bb & 1):                            # more effects?
                return hl

    def read_if_escape(self, a, hl):
        """0-14 is the value; 15 means an 8-bit one follows."""
        if a < 15:
            return a, hl
        return self.b(hl), hl + 1

    def fx_reset(self, t, a, hl):                       # 000
        t.inv_vol = a
        t.pud_used = 0
        t.arp_used = 0
        t.arp_val = 0                                   # unlike the pitch
        t.pit_used = 0
        return hl

    def fx_volume(self, t, a, hl):                      # 001
        t.inv_vol = a
        return hl

    def fx_pitch_up_down(self, t, a, hl):               # 010
        if a & 1:                                       # rra -> the 's' bit
            t.pud_used = 255
            t.pitch_speed = self.b(hl) | (self.b(hl + 1) << 8)
            return hl + 2
        t.pud_used = 0
        return hl

    def fx_arpeggio_table(self, t, a, hl):             # 011
        a, hl = self.read_if_escape(a, hl)
        t.arp_used = a
        if a == 0:
            t.arp_val = 0                               # the pitch does not
            return hl
        addr = self.w(self.pt_arp_tbl + ((a * 2) & 0xFF))
        t.arp_orig_speed = t.arp_speed = self.b(addr)
        t.pt_arp = addr + 1
        t.arp_off = 0
        t.arp_step = 0
        return hl

    def fx_pitch_table(self, t, a, hl):                 # 100
        a, hl = self.read_if_escape(a, hl)
        t.pit_used = a
        if a == 0:
            return hl
        addr = self.w(self.pt_pit_tbl + ((a * 2) & 0xFF))
        t.pit_orig_speed = t.pit_speed = self.b(addr)
        t.pt_pit = addr + 1
        t.pit_off = 0
        t.pit_step = 0
        return hl

    def fx_force_inst_speed(self, t, a, hl):            # 101
        a, hl = self.read_if_escape(a, hl)
        t.inst_speed = a
        return hl

    def fx_force_arp_speed(self, t, a, hl):             # 110
        a, hl = self.read_if_escape(a, hl)
        t.arp_speed = a                                 # the STEP is not reset
        return hl

    def fx_force_pit_speed(self, t, a, hl):             # 111
        a, hl = self.read_if_escape(a, hl)
        t.pit_speed = a
        return hl

    FX = [fx_reset, fx_volume, fx_pitch_up_down, fx_arpeggio_table,
          fx_pitch_table, fx_force_inst_speed, fx_force_arp_speed,
          fx_force_pit_speed]

    # ---- per-frame effect state -------------------------------------------
    def manage_effects(self, t):
        if t.pud_used:
            self.note('frame:pitch-up-down')
            # A 24-bit accumulator, integer:integer:decimal, and the speed is
            # a 16-bit quantity in units of 1/256.
            v = (t.pitch_int << 8) | t.pitch_dec
            sp = t.pitch_speed
            if sp & 0x8000:
                v = (v - (sp & 0x7FFF)) & 0xFFFFFF      # res 7,d then sbc
            else:
                v = (v + sp) & 0xFFFFFF
            t.pitch_dec = v & 0xFF
            t.pitch_int = (v >> 8) & 0xFFFF

        if t.arp_used:
            self.note('frame:arpeggio-table')
            # The value at the CURRENT offset is played every frame, whether
            # or not the step advances - the Z80's comment says this is to
            # get a corner case of Force Arpeggio Speed right.
            t.arp_val = sra(self.b(t.pt_arp + t.arp_off))
            if t.arp_step >= t.arp_speed:
                t.arp_step = 0
                t.arp_off = (t.arp_off + 1) & 0xFF
                nxt = self.b(t.pt_arp + t.arp_off)
                if nxt & 1:                             # end: loop offset
                    # FAITHFUL: `rra` with the carry known to be 0, so this
                    # is a LOGICAL shift - not AKL's sign-extending one.
                    t.arp_off = nxt >> 1
            else:
                t.arp_step += 1

        if t.pit_used:
            self.note('frame:pitch-table')
            t.pit_val = sra(self.b(t.pt_pit + t.pit_off)) & 0xFFFF
            if t.pit_step >= t.pit_speed:
                t.pit_step = 0
                t.pit_off = (t.pit_off + 1) & 0xFF
                nxt = self.b(t.pt_pit + t.pit_off)
                if nxt & 1:
                    t.pit_off = nxt >> 1
            else:
                t.pit_step += 1

    # ---- sound stream -----------------------------------------------------
    def period_for_note(self, t, arp):
        n = (arp + t.base_note + t.arp_val) & 0xFF
        p = PERIODS[n]
        if t.pit_used:
            p += t.pit_val
        # FAITHFUL: the track pitch is added UNCONDITIONALLY - there is no
        # test of pud_used here, unlike AKL. Stopping a pitch up/down leaves
        # the accumulated integer in place and it goes on being added until
        # a new instrument clears it. That is Arkos's behaviour, not a slip.
        p += t.pitch_int
        return p & 0xFFFF

    def adjust_volume(self, a, t):
        v = (a & 0x0F) - t.inv_vol
        return v if v >= 0 else 0

    def play_stream(self, t, ch, mixer):
        hl = t.pt_inst
        while True:
            bb = self.b(hl)
            hl += 1

            if not (bb & 1):
                if bb & 2:
                    typ = 'soft-to-hard'
                elif bb & 4:
                    # End of sound: the loop address follows. The pointer is
                    # stored before looping so that a sound sitting on its
                    # own last line does not re-walk the loop every frame.
                    hl = self.w(hl)
                    t.pt_inst = hl
                    continue
                else:
                    typ = 'nsnh'
            else:
                typ = 'soft-and-hard' if bb & 2 else 'software'

            if typ == 'nsnh':
                self.note('inst:no-soft-no-hard')
                mixer |= (1 << ch)                      # tone off
                if self.trace is not None:
                    self.inst_trace.append(
                        {'at': hl - 1, 'vol': (bb >> 3) & 0x0F, 'typ': typ})
                self.regs[8 + ch] = self.adjust_volume(bb >> 3, t)
                if bb & 0x80:
                    self.note('inst:noise')
                    self.regs[6] = self.b(hl)
                    hl += 1
                    mixer &= ~(8 << ch)                 # noise on
                break

            if typ == 'software':
                self.note('inst:software')
                if self.trace is not None:
                    self.inst_trace.append(
                        {'at': hl - 1, 'vol': (bb >> 2) & 0x0F, 'typ': typ})
                self.regs[8 + ch] = self.adjust_volume(bb >> 2, t)
                arp = 0
                if bb & 0x80:                           # arpeggio and/or noise
                    a = self.b(hl)
                    hl += 1
                    arp = sra(a)
                    if a & 1:
                        self.note('inst:noise')
                        self.regs[6] = self.b(hl)
                        hl += 1
                        mixer &= ~(8 << ch)
                p = self.period_for_note(t, arp)
                if bb & 0x40:                           # instrument pitch
                    self.note('inst:pitch')
                    p = (p + (self.b(hl) | (self.b(hl + 1) << 8))) & 0xFFFF
                    hl += 2
                self.regs[2 * ch] = p & 0xFF
                self.regs[2 * ch + 1] = (p >> 8) & 0xFF
                break

            # ---- the two hardware types share their front half ----
            self.note('inst:%s' % typ)
            if self.trace is not None:
                self.inst_trace.append({'at': hl - 1, 'vol': None, 'typ': typ})
            self.r13 = ENV_BASE + (2 if bb & 8 else 0)
            self.regs[8 + ch] = 16                      # envelope volume
            arp = 0
            if bb & 0x80:
                # FAITHFUL: the hardware paths read the arpeggio RAW, where
                # the software path takes an SRA of it.
                arp = self.b(hl)
                hl += 1
            p = self.period_for_note(t, arp)
            if bb & 4:
                p = (p + (self.b(hl) | (self.b(hl + 1) << 8))) & 0xFFFF
                hl += 2
            self.regs[2 * ch] = p & 0xFF
            self.regs[2 * ch + 1] = (p >> 8) & 0xFF

            if typ == 'soft-and-hard':
                self.regs[11] = self.b(hl)
                hl += 1
                self.regs[12] = self.b(hl)
                hl += 1
            else:
                # FAITHFUL: AKM's ratio is NOT inverted. AKL's is, and that
                # one difference is the whole of what AKM.md means by "the
                # Instrument format is the same as the Lightweight format,
                # EXCEPT that the encoded ratio is NOT inverted".
                n = (bb >> 4) & 7
                q, carry = p, 0
                for _ in range(n):
                    carry = q & 1
                    q >>= 1
                if n and carry:
                    q += 1
                self.regs[11] = q & 0xFF
                self.regs[12] = (q >> 8) & 0xFF
            break

        if t.inst_step >= t.inst_speed:
            t.pt_inst = hl
            t.inst_step = 0
        else:
            t.inst_step += 1
        return mixer

    # ---- one frame --------------------------------------------------------
    def play(self):
        self.tick = (self.tick + 1) & 0xFF
        if self.tick == self.speed:
            if self.pat_height == 0:
                self.read_linker()
            else:
                self.pat_height -= 1
            for t in self.tr:
                self.read_track(t)
            self.tick = 0

        mixer = 0x38                            # tone on, noise off, all three
        for ch, t in enumerate(self.tr):
            self.manage_effects(t)
            mixer = self.play_stream(t, ch, mixer)
        self.regs[7] = mixer

        if self.r13 != self.r13_old:
            self.r13_old = self.r13
            self.r13_sent = self.r13
        else:
            self.r13_sent = None
        self.regs[13] = self.r13
        return list(self.regs)
