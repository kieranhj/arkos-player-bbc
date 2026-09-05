"""Reference AKL ("lightweight") player: a transcription of Arkos Tracker 2's
PlayerLightweight.asm (Z80) into Python, producing the 14 AY registers a frame.

Written to prove the format is understood BEFORE any 6502 is written. It is
checked against edgea.ym - the register log SongToYm.exe produced from the same
song with Arkos's own full-fat player - frame for frame.
"""

PERIODS = [
    3822, 3608, 3405, 3214, 3034, 2863, 2703, 2551, 2408, 2273, 2145, 2025,
    1911, 1804, 1703, 1607, 1517, 1432, 1351, 1276, 1204, 1136, 1073, 1012,
    956, 902, 851, 804, 758, 716, 676, 638, 602, 568, 536, 506,
    478, 451, 426, 402, 379, 358, 338, 319, 301, 284, 268, 253,
    239, 225, 213, 201, 190, 179, 169, 159, 150, 142, 134, 127,
    119, 113, 106, 100, 95, 89, 84, 80, 75, 71, 67, 63,
    60, 56, 53, 50, 47, 45, 42, 40, 38, 36, 34, 32,
    30, 28, 27, 25, 24, 22, 21, 20, 19, 18, 17, 16,
    15, 14, 13, 13, 12, 11, 11, 10, 9, 9, 8, 8,
    7, 7, 7, 6, 6, 6, 5, 5, 5, 4, 4, 4,
    4, 4, 3, 3, 3, 3, 3, 2,
]
PERIODS += [0] * (128 - len(PERIODS))          # the table stops at 126; pad


ENV_BASE = 8      # the format's own shapes; see lib/aklplayer.asm.
                  # EDGEA needs 12. THIS MUST MATCH THE PLAYER'S.


class AklDataError(Exception):
    """The AKL stream references data outside itself - an export fault."""


def s8(v):
    return v - 256 if v & 0x80 else v


FIELDS = (
    'wait transp base_note inst_step inst_speed inv_vol pt_track pt_inst '
    'pt_base_inst pud_used pitch_dec pitch_speed pitch_int arp_used arp_off '
    'arp_val pt_arp pt_used pit_off pit_val pt_pit'
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
        self.pt_inst_tbl = self.w(base + 5)
        self.pt_arp_tbl = self.w(base + 7)
        self.pt_pit_tbl = self.w(base + 9)
        ss = self.w(base + 11 + subsong * 2)
        self.speed = self.b(ss)
        self.linker = ss + 1
        self.tick = (self.speed - 1) & 0xFF
        self.pat_height = 0
        self.prev_height = 0
        self.tr = [Track(), Track(), Track()]
        p = self.w(self.pt_inst_tbl) + 1        # the empty instrument, past its speed
        for t in self.tr:
            t.pt_inst = t.pt_base_inst = p
        self.regs = [0] * 14
        self.r13 = 0
        self.r13_old = 0
        self.r13_sent = None
        self.loops = 0

    # ---- memory -----------------------------------------------------------
    def b(self, a):
        o = a - self.base
        if not 0 <= o < len(self.d):
            raise AklDataError(
                'read of &%04X, outside the song (&%04X-&%04X). The exported '
                'data is asking for something it does not contain - see '
                'docs/format-akl.md, "The exporter can emit unplayable data".'
                % (a, self.base, self.base + len(self.d) - 1))
        return self.d[o]

    def w(self, a):
        o = a - self.base
        return self.d[o] | (self.d[o + 1] << 8)

    def note(self, k):
        self.stats[k] = self.stats.get(k, 0) + 1

    # ---- linker -----------------------------------------------------------
    def read_linker(self):
        hl = self.linker
        while True:
            for t in self.tr:
                t.wait = 0
            a = self.b(hl)
            hl += 1
            if not (a & 1):                     # end of song: loop
                hl = self.w(hl)
                self.loops += 1
                continue
            flags = a >> 1
            if flags & 1:                       # new speed
                self.speed = self.b(hl)
                hl += 1
                self.note('linker:speed')
            if (flags >> 1) & 1:                # new height
                self.prev_height = self.b(hl)
                hl += 1
            self.pat_height = self.prev_height
            if (flags >> 2) & 1:                # new transpositions
                for t in self.tr:
                    t.transp = self.b(hl)
                    hl += 1
                self.note('linker:transposition')
            for t in self.tr:
                t.pt_track = self.w(hl)
                hl += 2
            self.linker = hl
            return

    # ---- track ------------------------------------------------------------
    def read_track(self, t):
        if t.wait:
            t.wait -= 1
            return
        hl = t.pt_track
        bb = self.b(hl)
        hl += 1
        a = bb & 0x3F
        if a < 60:
            note = a + 24
        elif a == 60:
            self.note('cell:effect-only')
            t.pt_track = self.read_effect(t, hl)
            return
        elif a == 61:
            self.note('cell:wait-long')
            t.wait = self.b(hl)
            t.pt_track = hl + 1
            return
        elif a == 62:
            self.note('cell:wait-short')
            t.wait = (bb >> 6) & 3
            t.pt_track = hl
            return
        else:
            self.note('cell:escape-note')
            note = self.b(hl)
            hl += 1
        t.base_note = (note + t.transp) & 0xFF

        if bb & 0x80:                           # new instrument
            n = self.b(hl)
            hl += 1
            p = self.w(self.pt_inst_tbl + n)    # n is already the number * 2
            t.inst_speed = self.b(p)
            t.pt_inst = t.pt_base_inst = p + 1
        else:
            t.pt_inst = t.pt_base_inst
        t.inst_step = 0

        t.pud_used = 0                          # reset the track pitch...
        t.pitch_int = 0                         # ...but NOT its decimal part
        t.arp_off = 0
        t.pit_off = 0

        if bb & 0x40:                           # effect present
            hl = self.read_effect(t, hl)
        t.pt_track = hl

    # ---- effects ----------------------------------------------------------
    def read_effect(self, t, hl):
        bb = self.b(hl)
        hl += 1
        num = bb >> 5
        self.note('fx%d' % num)
        if num == 0:                            # reset
            t.inv_vol = bb & 0x0F
            self.do_reset(t)
        elif num == 1:                          # arpeggio table
            self.set_arp(t, bb & 0x1F)
        elif num == 2:                          # pitch table
            self.set_pit(t, bb & 0x1F)
        elif num == 3:                          # pitch up/down
            if bb & 1:
                hl = self.start_pud(t, hl)
            else:
                t.pud_used = 0
        elif num == 4:                          # volume + maybe pitch up/down
            t.inv_vol = bb & 0x0F
            if bb & 0x10:
                hl = self.start_pud(t, hl)
        elif num == 5:                          # volume + arpeggio table
            t.inv_vol = bb & 0x0F
            self.set_arp(t, self.b(hl))
            hl += 1
        elif num == 6:                          # reset + arpeggio table
            t.inv_vol = bb & 0x0F
            self.do_reset(t)
            self.set_arp(t, self.b(hl))
            hl += 1
        else:
            raise AssertionError('effect 7 is unused')
        return hl

    def do_reset(self, t):
        t.pud_used = 0
        t.arp_used = 0
        t.arp_val = 0
        t.pt_used = 0

    def start_pud(self, t, hl):
        t.pud_used = 255
        t.pitch_speed = self.b(hl) | (self.b(hl + 1) << 8)
        return hl + 2

    def set_arp(self, t, n):
        t.arp_used = n
        if n == 0:
            t.arp_val = 0
        else:
            t.pt_arp = self.w(self.pt_arp_tbl + n * 2)
            t.arp_off = 0

    def set_pit(self, t, n):
        t.pt_used = n
        if n:
            t.pt_pit = self.w(self.pt_pit_tbl + n * 2)
            t.pit_off = 0

    def manage_effects(self, t):
        if t.pud_used:
            self.note('frame:pitch-up-down')
            v = (t.pitch_int << 8) | t.pitch_dec        # 24 bits: int:int:dec
            sp = t.pitch_speed
            if sp & 0x8000:
                v = (v - (sp & 0x7FFF)) & 0xFFFFFF
            else:
                v = (v + sp) & 0xFFFFFF
            t.pitch_dec = v & 0xFF
            t.pitch_int = (v >> 8) & 0xFFFF
        if t.arp_used:
            self.note('frame:arpeggio-table')
            off = t.arp_off
            for _hop in range(257):
                a = self.b(t.pt_arp + off)
                if a & 1:                                # end: loop offset
                    # The Z80 does `sra a` then `ld l,a : ld h,0`, so the loop
                    # offset is sign-extended AND THEN USED AS UNSIGNED 0-255.
                    # Without the mask this indexes backwards off the song.
                    off = (s8(a) >> 1) & 0xFF
                    t.arp_off = off
                    continue
                t.arp_val = s8(a) >> 1
                break
            else:
                raise AklDataError(
                    'arpeggio %d at &%04X loops without ever giving a value: '
                    'its end markers point at each other. No player can play '
                    'this - the 6502 spins, and so did this reference until '
                    'the hop count was bounded.' % (t.arp_used, t.pt_arp))
            t.arp_off = (off + 1) & 0xFF
        if t.pt_used:
            self.note('frame:pitch-table')
            off = t.pit_off
            for _hop in range(257):
                a = self.b(t.pt_pit + off)
                if a & 1:
                    off = (s8(a) >> 1) & 0xFF            # as above
                    t.pit_off = off
                    continue
                t.pit_val = s8(a) >> 1
                break
            else:
                raise AklDataError(
                    'pitch table %d at &%04X loops without ever giving a '
                    'value: its end markers point at each other.'
                    % (t.pt_used, t.pt_pit))
            t.pit_off = (off + 1) & 0xFF

    # ---- sound stream -----------------------------------------------------
    def period_for_note(self, t, arp):
        n = (arp + t.base_note + t.arp_val) & 0xFF
        p = PERIODS[n & 0x7F]
        if t.pt_used:
            p += t.pit_val
        if t.pud_used:
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
            typ = bb & 3

            if typ == 0:
                if bb & 4:                              # end of sound: loop
                    hl = self.w(hl)
                    t.pt_inst = hl
                    continue
                self.note('inst:no-soft-no-hard')
                mixer |= (1 << ch)                      # tone off
                self.regs[8 + ch] = self.adjust_volume(bb >> 3, t)
                if bb & 0x80:
                    self.note('inst:noise')
                    self.regs[6] = self.b(hl)
                    hl += 1
                    mixer &= ~(8 << ch)                 # noise on
                break

            if typ == 1:                                # software
                self.note('inst:software')
                self.regs[8 + ch] = self.adjust_volume(bb >> 2, t)
                arp = 0
                if bb & 0x80:                           # arpeggio and/or noise
                    a = self.b(hl)
                    hl += 1
                    arp = s8(a) >> 1
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

            # 2 = software to hardware, 3 = software and hardware
            self.note('inst:hardware-%d' % typ)
            self.r13 = ENV_BASE + (2 if bb & 8 else 0)
            self.regs[8 + ch] = 16                      # envelope volume
            arp = 0
            if bb & 0x80:
                arp = self.b(hl)
                hl += 1
            p = self.period_for_note(t, arp)
            if bb & 4:
                p = (p + (self.b(hl) | (self.b(hl + 1) << 8))) & 0xFFFF
                hl += 2
            self.regs[2 * ch] = p & 0xFF
            self.regs[2 * ch + 1] = (p >> 8) & 0xFF
            if typ == 3:
                self.regs[11] = self.b(hl)
                hl += 1
                self.regs[12] = self.b(hl)
                hl += 1
            else:
                n = 7 - ((bb >> 4) & 7)                 # r is the INVERTED ratio
                q = p
                carry = 0
                for _ in range(n):
                    carry = q & 1
                    q >>= 1
                if n and carry:
                    q += 1
                self.regs[11] = q & 0xFF
                self.regs[12] = (q >> 8) & 0xFF
            break

        if t.inst_step == t.inst_speed:
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
