\ ******************************************************************
\ * akmplayer.asm - Arkos Tracker "minimalist" (AKM) replay, 6502
\ *
\ * A port of PlayerAkm.asm (Z80, Targhan/Arkos) to the 6502. AKM is
\ * the smallest Arkos format - 3,654 bytes for Edge Grinder's 349
\ * seconds against AKL's 4,741 - and there was no 6502 player for it
\ * anywhere before this one.
\ *
\ * It produces the fourteen AY-3-8912 registers into ay_regs each
\ * frame. It does NOT convert them to the SN76489 - that is a separate
\ * layer, and a separate measurement.
\ *
\ * A REWRITE, NOT A TRANSCRIPTION. The Z80 uses `ld sp,` as a data
\ * pointer to push the PSG registers out through a RET table, and it
\ * self-modifies an instruction operand for every value it reads from
\ * the song header. Neither travels. What is reproduced here is its
\ * ARITHMETIC, statement for statement.
\ *
\ * Conventions, the same as lib/aklplayer.asm:
\ *   X  = channel, 0-2, for the whole of a channel's processing.
\ *   Y  = byte offset into the track / instrument being read.
\ *   Per-channel state lives in 3-byte arrays indexed by X.
\ *
\ * Deviations from the Z80, both agreed with KC before they were built
\ * and both recorded in PLAN.md:
\ *
\ *   - The MIXER is assembled the way lib/aklplayer.asm assembles it,
\ *     with per-channel masks into one byte, rather than the Z80's
\ *     rotate-a-register-through-three-channels, which leaves bits 6
\ *     and 7 as whatever fell out of the last shift. Identical in every
\ *     bit that can be heard (decision 8).
\ *   - The pitch up/down speed has its sign split off at parse time
\ *     (t_pspd_hi masked, sign in t_pneg) rather than masked at every
\ *     use, exactly as aklplayer.asm does. Same results, less work in
\ *     the per-frame path.
\ ******************************************************************

\ ******************************************************************
\ * ENV_BASE IS THE HOST'S TO DEFINE, before it INCLUDEs this file.
\ *
\ * AKM stores ONE BIT of envelope shape and it means shape ENV_BASE or
\ * ENV_BASE + 2 - the same limitation AKL has, and handled the same
\ * way. The format defines those as 8 and 10, so ENV_BASE = 8 is right
\ * for any tune that really uses 8 or 10, which is most of them. A tune
\ * whose real envelope AKM could NOT encode gets a substitute on export
\ * and the pair has to be shifted back: Edge Grinder's EDGEA is
\ * envelope 12 throughout and needs ENV_BASE = 12.
\ *
\ * It is not defaulted here on purpose. It is a property of the SONG,
\ * not of the player. tools/arkos.py's envelope_base() works it out and
\ * serves AKL and AKM alike; getting it wrong shows up as `env shape`
\ * in tools/verify/verify.py.
\ ******************************************************************

\ ******************************************************************
\ * akm_init - A/X = LO/HI of the song, Y = subsong index
\ ******************************************************************
.akm_init
{
    sta tptr : stx tptr+1
    sty tmp

    \ Song header: three table pointers, then the subsong pointers.
    \ The arpeggio and pitch pointers are already biased by -2 by the
    \ exporter, because entry 0 of each is never encoded.
    ldy #0
    lda (tptr),y : sta inst_tbl   : iny
    lda (tptr),y : sta inst_tbl+1 : iny
    lda (tptr),y : sta arp_tbl    : iny
    lda (tptr),y : sta arp_tbl+1  : iny
    lda (tptr),y : sta pit_tbl    : iny
    lda (tptr),y : sta pit_tbl+1

    \ Subsong pointer, at header + 6 + 2 * index.
    lda tmp : asl a : clc : adc #6 : tay
    lda (tptr),y : sta ptr
    iny
    lda (tptr),y : sta ptr+1

    \ Subsong header: thirteen bytes, in PLY_AKM_InitVars_Start's order.
    ldy #0
    lda (ptr),y : sta note_tbl    : iny
    lda (ptr),y : sta note_tbl+1  : iny
    lda (ptr),y : sta track_idx   : iny
    lda (ptr),y : sta track_idx+1 : iny
    lda (ptr),y : sta akm_speed   : iny
    lda (ptr),y : sta prim_inst   : iny
    lda (ptr),y : sta sec_inst    : iny
    lda (ptr),y : sta prim_wait   : iny
    lda (ptr),y : sta sec_wait    : iny
    lda (ptr),y : sta def_note    : iny
    lda (ptr),y : sta def_inst    : iny
    lda (ptr),y : sta def_wait    : iny
    lda (ptr),y : sta note_fx_flag

    \ The linker follows the subsong header.
    lda ptr   : clc : adc #13 : sta lnk
    lda ptr+1 : adc #0 : sta lnk+1

    \ Force a new line on the first play.
    lda akm_speed
    sec : sbc #1 : sta akm_tick

    \ Clear the per-channel state.
    lda #0
    sta akm_height : sta akm_prevh : sta fxflag : sta r13 : sta r13_old
    ldx #(state_end - state_start - 1)
.clr
    sta state_start,x
    dex
    bpl clr

    \ Every channel starts on instrument 0 - the empty one - past its
    \ speed byte, so that a song not opening with an instrument on all
    \ three channels still has something to read.
    lda inst_tbl   : sta tptr
    lda inst_tbl+1 : sta tptr+1
    ldy #0
    lda (tptr),y : sta iptr
    iny
    lda (tptr),y : sta iptr+1
    lda iptr   : clc : adc #1 : sta iptr
    lda iptr+1 : adc #0 : sta iptr+1
    ldx #2
.ins
    lda iptr   : sta t_inst_lo,x
    lda iptr+1 : sta t_inst_hi,x
    dex
    bpl ins
    rts
}

\ ******************************************************************
\ * akm_play - one frame. Fills ay_regs.
\ ******************************************************************
.akm_play
{
    inc akm_tick
    lda akm_tick
    cmp akm_speed
    bne no_new_line

    lda akm_height
    bne dec_height
    jsr read_linker
    jmp read_lines
.dec_height
    dec akm_height
.read_lines
    ldx #0
.rl_loop
    jsr read_track
    inx
    cpx #3
    bne rl_loop
    lda #0
    sta akm_tick

.no_new_line
    lda #&38                    \ tone on, noise off, all three channels
    sta mixer
    ldx #0
.ch_loop
    jsr manage_effects
    jsr play_stream
    inx
    cpx #3
    bne ch_loop

    \ ---- assemble the register file ----
    lda chan_per_lo+0 : sta ay_regs+0
    lda chan_per_hi+0 : sta ay_regs+1
    lda chan_per_lo+1 : sta ay_regs+2
    lda chan_per_hi+1 : sta ay_regs+3
    lda chan_per_lo+2 : sta ay_regs+4
    lda chan_per_hi+2 : sta ay_regs+5
    lda noise_reg     : sta ay_regs+6
    lda mixer         : sta ay_regs+7
    lda chan_vol+0    : sta ay_regs+8
    lda chan_vol+1    : sta ay_regs+9
    lda chan_vol+2    : sta ay_regs+10
    lda reg11         : sta ay_regs+11
    lda reg12         : sta ay_regs+12

    \ R13 is only sent when it changes - writing it restarts the envelope
    lda r13
    cmp r13_old
    beq same_r13
    sta r13_old
    sta ay_regs+13
    rts
.same_r13
    lda #255                    \ "not written this frame"
    sta ay_regs+13
    rts
}

\ ******************************************************************
\ * read_linker - a new pattern: speed, height, transpositions, tracks
\ *
\ * The state byte is consumed by eight shifts in all - one for the
\ * speed bit, one for the height bit, then two per channel - so it is
\ * fully used up by the time the three channels have been done.
\ ******************************************************************
.read_linker
{
    lda lnk : sta ptr
    lda lnk+1 : sta ptr+1
.top
    \ On a new pattern every channel's wait is cleared and its three
    \ escape values go back to the subsong's defaults.
    ldx #2
.rst
    lda #0        : sta t_wait,x
    lda def_note  : sta t_esc_note,x
    lda def_inst  : sta t_esc_inst,x
    lda def_wait  : sta t_esc_wait,x
    dex
    bpl rst

    ldy #0
    lda (ptr),y
    iny
    sta lflags

    lsr lflags                  \ C = speed change, or end of song
    bcc no_speed
    lda (ptr),y
    iny
    bne set_speed
    \ End of song: the loop address in the linker follows.
    lda (ptr),y : sta tmp
    iny
    lda (ptr),y : sta ptr+1
    lda tmp : sta ptr
    jmp top
.set_speed
    sta akm_speed
.no_speed

    lsr lflags                  \ C = new height
    bcc no_height
    lda (ptr),y
    iny
    sta akm_prevh
.no_height
    lda akm_prevh
    sta akm_height

    ldx #0
.ch
    jsr transp_and_track
    inx
    cpx #3
    bne ch

    tya
    clc : adc ptr : sta lnk
    lda ptr+1 : adc #0 : sta lnk+1
    rts
}

\ ******************************************************************
\ * transp_and_track - X = channel, Y = offset into (ptr). Advances Y.
\ * Consumes two bits of lflags.
\ ******************************************************************
.transp_and_track
{
    lsr lflags                  \ C = new transposition
    bcc no_transp
    lda (ptr),y
    iny
    sta t_transp,x
.no_transp

    lsr lflags                  \ C = new track
    bcc no_track

    lda (ptr),y
    iny
    sta tmp                     \ keep the raw byte: bit 7 is the flag
    asl a
    bcc offset

    \ A reference. The shift has already made it index * 2.
    sty iofs
    clc : adc track_idx : sta tptr
    lda track_idx+1 : adc #0 : sta tptr+1
    ldy #0
    lda (tptr),y : sta t_track_lo,x : sta t_start_lo,x
    iny
    lda (tptr),y : sta t_track_hi,x : sta t_start_hi,x
    ldy iofs
    rts

.offset
    \ An offset from just PAST the two bytes that encode it - which is
    \ what Arkos's own source export says too, emitting the pair as
    \ ((Track - ($ + 2)) & #ff00) / 256 and ((Track - ($ + 1)) & 255).
    \ tmp is the MSB (bit 7 known clear), the next byte the LSB.
    lda (ptr),y
    iny
    sta tmp+1
    tya
    clc : adc ptr : sta tptr    \ tptr = the address past both bytes
    lda ptr+1 : adc #0 : sta tptr+1
    lda tptr   : clc : adc tmp+1 : sta t_track_lo,x : sta t_start_lo,x
    lda tptr+1 : adc tmp         : sta t_track_hi,x : sta t_start_hi,x
    rts

.no_track
    \ The same track plays again, from its start.
    lda t_start_lo,x : sta t_track_lo,x
    lda t_start_hi,x : sta t_track_hi,x
    rts
}

\ ******************************************************************
\ * read_track - X = channel. One cell of this channel's track.
\ ******************************************************************
.read_track
{
    lda t_wait,x
    beq read
    dec t_wait,x
    rts

.read
    lda t_track_lo,x : sta ptr
    lda t_track_hi,x : sta ptr+1
    ldy #0
.get_byte
    lda (ptr),y
    iny
    sta cell
    and #&0f
    cmp note_fx_flag            \ 12 if the song has effects, else 13
    bcc note_ref
    cmp #12
    beq note_and_fx
    cmp #13
    beq empty_note
    cmp #14
    beq new_escape

    \ 15: the same escape note as last time.
    lda t_esc_note,x
    jmp have_note

.note_and_fx
    \ "Note and effects": this byte exists only to raise the flag, and
    \ the whole cell is re-encoded in the NEXT one. Reached only when
    \ the song has effects at all - when it has not, the header's flag
    \ is 13 and a nibble of 12 is an ordinary note reference.
    lda #1
    sta fxflag
    jmp get_byte

.empty_note
    \ No note. The instrument bits are diverted to say whether there
    \ are effects; there is no instrument to read either way.
    lda cell
    and #&10
    beq no_cell_fx
    lda #1
    sta fxflag
.no_cell_fx
    jmp read_wait

.new_escape
    lda (ptr),y
    iny
    sta t_esc_note,x
    jmp have_note

.note_ref
    \ 0-11, or 0-12: an index into the subsong's note table.
    sty iofs
    tay
    lda (note_tbl),y
    ldy iofs

.have_note
    clc
    adc t_transp,x
    sta t_base_note,x

    \ ---- the instrument ----
    lda cell
    and #&30
    beq same_esc_inst
    cmp #&10
    beq use_prim
    cmp #&20
    beq use_sec
    lda (ptr),y                 \ a new escape instrument
    iny
    sta t_esc_inst,x
    jmp got_inst
.same_esc_inst
    lda t_esc_inst,x
    jmp got_inst
.use_prim
    lda prim_inst
    jmp got_inst
.use_sec
    lda sec_inst

.got_inst
    \ A = the instrument number. Its address is at inst_tbl + n * 2;
    \ only 127 instruments are possible, so the shift cannot overflow
    \ anything the format can express.
    asl a
    sty iofs
    clc : adc inst_tbl : sta tptr
    lda inst_tbl+1 : adc #0 : sta tptr+1
    ldy #0
    lda (tptr),y : sta iptr
    iny
    lda (tptr),y : sta iptr+1
    ldy #0
    lda (iptr),y : sta t_inst_speed,x       \ the instrument's speed header
    lda iptr   : clc : adc #1 : sta t_inst_lo,x
    lda iptr+1 : adc #0 : sta t_inst_hi,x
    ldy iofs

    \ A new instrument resets the track pitch and both table offsets -
    \ but NOT the pitch's decimal part, which the Z80 leaves alone.
    lda #0
    sta t_inst_step,x
    sta t_pud,x
    sta t_pint_lo,x
    sta t_pint_hi,x
    sta t_arp_off,x
    sta t_arp_step,x
    sta t_pit_off,x
    sta t_pit_step,x
    lda t_arp_orig,x : sta t_arp_speed,x
    lda t_pit_orig,x : sta t_pit_speed,x

\ ---- the wait, then any effects ----------------------------------
.read_wait
    lda cell
    and #&c0
    beq same_esc_wait
    cmp #&40
    beq use_prim_wait
    cmp #&80
    beq use_sec_wait
    lda (ptr),y                 \ a new escape wait
    iny
    sta t_esc_wait,x
    jmp store_wait
.same_esc_wait
    lda t_esc_wait,x
    jmp store_wait
.use_prim_wait
    lda prim_wait
    jmp store_wait
.use_sec_wait
    lda sec_wait
.store_wait
    sta t_wait,x

    lda fxflag
    beq store_ptr
    lda #0
    sta fxflag
    jsr read_effects

.store_ptr
    tya
    clc : adc ptr : sta t_track_lo,x
    lda ptr+1 : adc #0 : sta t_track_hi,x
    rts
}

\ ******************************************************************
\ * read_effects - X = channel, Y = offset into (ptr). Advances Y.
\ * Bit 0 of each effect byte says another follows.
\ ******************************************************************
.read_effects
{
.loop
    lda (ptr),y
    iny
    sta cell
    jsr do_effect
    lda cell
    lsr a
    bcs loop
    rts
}

\ Effect byte: ddddeeem. e = the effect, d = its data, m = "one more".
.do_effect
{
    lda cell
    and #&0e                    \ the effect number, already doubled
    sty iofs_e
    tay
    lda fx_vec+0,y : sta jvec
    lda fx_vec+1,y : sta jvec+1
    ldy iofs_e
    lda cell
    lsr a : lsr a : lsr a : lsr a       \ A = the data nibble
    jmp (jvec)                          \ each handler ends in RTS

.fx_vec
    equw fx_reset                       \ 000
    equw fx_volume                      \ 001
    equw fx_pud                         \ 010
    equw fx_arp                         \ 011
    equw fx_pit                         \ 100
    equw fx_force_inst                  \ 101
    equw fx_force_arp                   \ 110
    equw fx_force_pit                   \ 111
}
.iofs_e     skip 1

\ Reads the next byte as the value if the nibble is 15, else the
\ nibble IS the value (0-14).
.read_if_escape
{
    cmp #15
    bcc out
    lda (ptr),y
    iny
.out
    rts
}

.fx_reset
{
    sta t_inv_vol,x
    lda #0
    sta t_pud,x
    sta t_arp_used,x
    sta t_arp_val,x             \ unlike the pitch, this must be cleared
    sta t_pit_used,x
    rts
}

.fx_volume
{
    sta t_inv_vol,x
    rts
}

.fx_pud
{
    lsr a                       \ C = pitch used, or pitch stopped
    bcs start
    lda #0
    sta t_pud,x
    rts
.start
    lda #255
    sta t_pud,x
    lda (ptr),y
    iny
    sta t_pspd_lo,x
    lda (ptr),y
    iny
    sta t_pspd_hi,x
    and #&80                    \ bit 15 is the sign; split it off now
    sta t_pneg,x
    lda t_pspd_hi,x
    and #&7f
    sta t_pspd_hi,x
    rts
}

.fx_arp
{
    jsr read_if_escape
    sta t_arp_used,x
    bne start
    sta t_arp_val,x             \ stopped: the value must go too
    rts
.start
    sty iofs
    asl a
    clc : adc arp_tbl : sta tptr
    lda arp_tbl+1 : adc #0 : sta tptr+1
    ldy #0
    lda (tptr),y : sta tmp
    iny
    lda (tptr),y : sta tptr+1
    lda tmp : sta tptr
    ldy #0
    lda (tptr),y                \ the arpeggio's own speed
    sta t_arp_orig,x
    sta t_arp_speed,x
    lda tptr   : clc : adc #1 : sta t_arp_lo,x
    lda tptr+1 : adc #0 : sta t_arp_hi,x
    lda #0
    sta t_arp_off,x
    sta t_arp_step,x
    ldy iofs
    rts
}

.fx_pit
{
    jsr read_if_escape
    sta t_pit_used,x
    bne start
    rts                         \ stopped: the value is NOT cleared
.start
    sty iofs
    asl a
    clc : adc pit_tbl : sta tptr
    lda pit_tbl+1 : adc #0 : sta tptr+1
    ldy #0
    lda (tptr),y : sta tmp
    iny
    lda (tptr),y : sta tptr+1
    lda tmp : sta tptr
    ldy #0
    lda (tptr),y
    sta t_pit_orig,x
    sta t_pit_speed,x
    lda tptr   : clc : adc #1 : sta t_pit_lo,x
    lda tptr+1 : adc #0 : sta t_pit_hi,x
    lda #0
    sta t_pit_off,x
    sta t_pit_step,x
    ldy iofs
    rts
}

\ The three "force speed" effects. The current STEP is deliberately not
\ reset - the Z80 says so, and says it is more compliant with the C++
\ player that way.
.fx_force_inst
{
    jsr read_if_escape
    sta t_inst_speed,x
    rts
}

.fx_force_arp
{
    jsr read_if_escape
    sta t_arp_speed,x
    rts
}

.fx_force_pit
{
    jsr read_if_escape
    sta t_pit_speed,x
    rts
}

\ ******************************************************************
\ * manage_effects - X = channel. The per-frame effect state.
\ ******************************************************************
.manage_effects
{
    \ ---- pitch up/down: a 24-bit accumulator, integer:integer:decimal,
    \ ---- and the speed is a 16-bit quantity in units of 1/256.
    lda t_pud,x
    beq no_pud
    lda t_pneg,x
    bne negative
    clc
    lda t_pdec,x    : adc t_pspd_lo,x : sta t_pdec,x
    lda t_pint_lo,x : adc t_pspd_hi,x : sta t_pint_lo,x
    lda t_pint_hi,x : adc #0          : sta t_pint_hi,x
    jmp no_pud
.negative
    sec
    lda t_pdec,x    : sbc t_pspd_lo,x : sta t_pdec,x
    lda t_pint_lo,x : sbc t_pspd_hi,x : sta t_pint_lo,x
    lda t_pint_hi,x : sbc #0          : sta t_pint_hi,x
.no_pud

    \ ---- the arpeggio table ----
    \ The value at the current offset is played EVERY frame, whether or
    \ not the step advances; the Z80 says this is to get a corner case
    \ of Force Arpeggio Speed right.
    lda t_arp_used,x
    beq no_arp
    lda t_arp_lo,x : sta tptr
    lda t_arp_hi,x : sta tptr+1
    ldy t_arp_off,x
    lda (tptr),y
    cmp #&80                    \ SRA: carry from bit 7, then rotate in
    ror a
    sta t_arp_val,x

    lda t_arp_step,x
    cmp t_arp_speed,x
    bcc arp_waiting
    lda #0
    sta t_arp_step,x
    iny                         \ advance, wrapping at 256 as the Z80 does
    tya
    sta t_arp_off,x
    lda (tptr),y
    lsr a                       \ C = end of the arpeggio
    bcc no_arp
    sta t_arp_off,x             \ A is the loop offset, logically shifted
    jmp no_arp
.arp_waiting
    inc t_arp_step,x
.no_arp

    \ ---- the pitch table: the same, but the value is 16-bit signed ----
    lda t_pit_used,x
    beq no_pit
    lda t_pit_lo,x : sta tptr
    lda t_pit_hi,x : sta tptr+1
    ldy t_pit_off,x
    lda (tptr),y
    cmp #&80
    ror a
    sta t_pitv_lo,x
    cmp #&80                    \ sign-extend it into the high byte
    lda #0
    bcc pit_pos
    lda #&ff
.pit_pos
    sta t_pitv_hi,x

    lda t_pit_step,x
    cmp t_pit_speed,x
    bcc pit_waiting
    lda #0
    sta t_pit_step,x
    iny
    tya
    sta t_pit_off,x
    lda (tptr),y
    lsr a
    bcc no_pit
    sta t_pit_off,x
    jmp no_pit
.pit_waiting
    inc t_pit_step,x
.no_pit
    rts
}

\ ******************************************************************
\ * play_stream - X = channel. Walks the instrument, sets the channel's
\ * volume, period, and any noise / hardware registers.
\ *
\ * The instrument format is AKL's, byte for byte, with ONE exception:
\ * the software-to-hardware ratio is NOT inverted. That is the whole
\ * of what AKM.md means by "the Instrument format is the same as the
\ * Lightweight format, EXCEPT that the encoded ratio is NOT inverted".
\ ******************************************************************
.play_stream
{
    lda t_inst_lo,x : sta iptr
    lda t_inst_hi,x : sta iptr+1
    ldy #0
.read
    lda (iptr),y
    sta cell
    iny
    lsr a
    bcs soft_or_sah
    lsr a
    bcc not_sth
    jmp soft_to_hard
.not_sth
    lsr a
    bcc nsnh

    \ End of sound: the loop address follows. The pointer is stored
    \ before looping so that a sound sitting on its own last line does
    \ not re-walk the loop every frame.
    lda (iptr),y : sta tmp
    iny
    lda (iptr),y : sta iptr+1
    lda tmp : sta iptr
    lda iptr   : sta t_inst_lo,x
    lda iptr+1 : sta t_inst_hi,x
    ldy #0
    jmp read

\ ---- no software, no hardware ------------------------------------
.nsnh
    lda cell
    lsr a : lsr a : lsr a
    jsr adjust_volume
    sta chan_vol,x
    lda mixer
    ora tone_bit,x              \ tone off
    sta mixer
    lda cell
    bpl store_ptr_j
    jsr read_noise
.store_ptr_j
    jmp store_ptr

\ ---- software, or software and hardware --------------------------
.soft_or_sah
    lsr a
    bcs soft_and_hard

    lda cell
    lsr a : lsr a
    jsr adjust_volume
    sta chan_vol,x

    lda #0
    sta tmp                     \ the instrument arpeggio
    lda cell
    bpl no_arp_noise
    lda (iptr),y
    iny
    sta tmp+1
    cmp #&80                    \ SRA: the signed arpeggio
    ror a
    sta tmp
    lda tmp+1
    lsr a
    bcc no_arp_noise
    jsr read_noise
.no_arp_noise
    lda tmp
    jsr period_for_note

    lda cell
    and #&40
    beq soft_store
    jsr add_inst_pitch
.soft_store
    lda per   : sta chan_per_lo,x
    lda per+1 : sta chan_per_hi,x
    jmp store_ptr

\ ---- hardware ----------------------------------------------------
.soft_and_hard
    jsr hard_common
    lda (iptr),y : sta reg11
    iny
    lda (iptr),y : sta reg12
    iny
    jmp store_ptr

.soft_to_hard
    jsr hard_common
    \ Hardware period = software period >> ratio, rounded. AKM's ratio
    \ is used AS-IS; AKL's is inverted and has to be subtracted from 7.
    lda cell
    lsr a : lsr a : lsr a : lsr a
    and #7
    beq no_shift
    tay
    clc
.shift
    lsr per+1
    ror per
    dey
    bne shift
    bcc no_round
    inc per
    bne no_round
    inc per+1
.no_round
    ldy iofs                    \ hard_common parked the instrument offset
.no_shift
    lda per   : sta reg11
    lda per+1 : sta reg12
    jmp store_ptr

\ ---- store the instrument pointer, honouring the instrument speed --
.store_ptr
    lda t_inst_step,x
    cmp t_inst_speed,x
    bcs speed_reached           \ step >= speed, unlike AKL's equality
    inc t_inst_step,x
    rts
.speed_reached
    tya
    clc : adc iptr : sta t_inst_lo,x
    lda iptr+1 : adc #0 : sta t_inst_hi,x
    lda #0
    sta t_inst_step,x
    rts
}

\ Shared by both hardware types: envelope shape, envelope volume,
\ optional arpeggio and pitch, and the software period.
.hard_common
{
    lda cell
    and #8
    beq shape_lo
    lda #ENV_BASE + 2
    bne set_shape
.shape_lo
    lda #ENV_BASE
.set_shape
    sta r13

    lda #16                     \ volume 16 = "use the envelope"
    sta chan_vol,x

    lda #0
    sta tmp
    lda cell
    bpl no_arp
    lda (iptr),y                \ the hardware paths read the arpeggio RAW,
    iny                         \ where the software path takes an SRA of it
    sta tmp
.no_arp
    lda tmp
    jsr period_for_note

    lda cell
    and #4
    beq no_pitch
    jsr add_inst_pitch
.no_pitch
    lda per   : sta chan_per_lo,x       \ the software period still plays
    lda per+1 : sta chan_per_hi,x
    sty iofs
    rts
}

\ A = the instrument's arpeggio. Leaves the channel period in per.
.period_for_note
{
    sty iofs
    clc
    adc t_base_note,x
    clc
    adc t_arp_val,x
    tay                         \ 8-bit and wrapping: the table has 256
    lda akm_per_lo,y : sta per
    lda akm_per_hi,y : sta per+1

    lda t_pit_used,x
    beq no_pit
    clc
    lda per   : adc t_pitv_lo,x : sta per
    lda per+1 : adc t_pitv_hi,x : sta per+1
.no_pit
    \ The track pitch is added UNCONDITIONALLY - there is no test of
    \ t_pud here, unlike AKL. Stopping a pitch up/down leaves what it
    \ accumulated in place, and it goes on being added until a new
    \ instrument clears it. That is Arkos's behaviour, not a slip.
    clc
    lda per   : adc t_pint_lo,x : sta per
    lda per+1 : adc t_pint_hi,x : sta per+1
    ldy iofs
    rts
}

\ Adds the instrument's own 16-bit pitch, at (iptr),y. Advances Y.
.add_inst_pitch
{
    clc
    lda (iptr),y
    adc per
    sta per
    iny
    lda (iptr),y
    adc per+1
    sta per+1
    iny
    rts
}

\ A = raw volume. Subtracts the track's inverted volume, clamped at 0.
.adjust_volume
{
    and #&0f
    sec
    sbc t_inv_vol,x
    bcs out
    lda #0
.out
    rts
}

\ Reads the noise value at (iptr),y, opens the noise channel. Advances Y.
.read_noise
{
    lda (iptr),y
    iny
    sta noise_reg
    lda mixer
    and noise_mask,x
    sta mixer
    rts
}

\ ******************************************************************
\ * tables and state
\ ******************************************************************
.noise_mask     equb &f7, &ef, &df

\ 256 note periods, lo/hi. NOT lib/akl_periods.asm - see the head of
\ that file and docs/format-akm.md.
INCLUDE "lib/akm_periods.asm"

.state_start
.t_wait         skip 3
.t_transp       skip 3
.t_base_note    skip 3
.t_esc_note     skip 3
.t_esc_inst     skip 3
.t_esc_wait     skip 3
.t_track_lo     skip 3
.t_track_hi     skip 3
.t_start_lo     skip 3
.t_start_hi     skip 3
.t_inst_lo      skip 3
.t_inst_hi      skip 3
.t_inst_step    skip 3
.t_inst_speed   skip 3
.t_inv_vol      skip 3
.t_pud          skip 3
.t_pneg         skip 3
.t_pdec         skip 3
.t_pspd_lo      skip 3
.t_pspd_hi      skip 3
.t_pint_lo      skip 3
.t_pint_hi      skip 3
.t_arp_used     skip 3
.t_arp_lo       skip 3
.t_arp_hi       skip 3
.t_arp_off      skip 3
.t_arp_step     skip 3
.t_arp_speed    skip 3
.t_arp_orig     skip 3
.t_arp_val      skip 3
.t_pit_used     skip 3
.t_pit_lo       skip 3
.t_pit_hi       skip 3
.t_pit_off      skip 3
.t_pit_step     skip 3
.t_pit_speed    skip 3
.t_pit_orig     skip 3
.t_pitv_lo      skip 3
.t_pitv_hi      skip 3
.chan_vol       skip 3
.chan_per_lo    skip 3
.chan_per_hi    skip 3
.noise_reg      skip 1
.reg11          skip 1
.reg12          skip 1
.r13            skip 1
.r13_old        skip 1
.state_end

\ The song header's table addresses. Only note_tbl is in zero page,
\ because only it is read through directly; the rest are added to an
\ index to make tptr.
.inst_tbl       skip 2
.arp_tbl        skip 2
.pit_tbl        skip 2
.track_idx      skip 2
.prim_inst      skip 1
.sec_inst       skip 1
.prim_wait      skip 1
.sec_wait       skip 1
.def_note       skip 1
.def_inst       skip 1
.def_wait       skip 1
.note_fx_flag   skip 1

\ ay_regs itself lives in lib/ay2sn.asm - it is the library's boundary
\ and every player in this repo fills the same fourteen bytes.
.akm_end
