\ ******************************************************************
\ * aklplayer.asm - Arkos Tracker 2 "lightweight" (AKL) replay, 6502
\ *
\ * A port of PlayerLightweight.asm (Z80, Targhan/Arkos) to the 6502,
\ * written to MEASURE what an Arkos tracker replay costs on a BBC
\ * before deciding whether to take that route for Edge Grinder.
\ *
\ * It produces the fourteen AY-3-8912 registers into ay_regs each
\ * frame. It does NOT convert them to the SN76489 - that is a separate
\ * layer, and a separate measurement.
\ *
\ * Conventions:
\ *   X  = channel, 0-2, for the whole of a channel's processing.
\ *   Y  = byte offset into the track / instrument being read.
\ *   Per-channel state lives in 3-byte arrays indexed by X.
\ *
\ * Deviation from the Z80, deliberate: the pitch up/down speed is
\ * stored with its sign split off at parse time (t_pspd_hi masked, sign
\ * in t_pneg) rather than masked at every use. Same results, less work
\ * in the per-frame path.
\ ******************************************************************

\ ******************************************************************
\ * ENV_BASE IS THE HOST'S TO DEFINE, before it INCLUDEs this file.
\ *
\ * AKL stores ONE BIT of envelope shape, and it means shape ENV_BASE or
\ * ENV_BASE + 2. The format defines those as 8 and 10, so ENV_BASE = 8
\ * is right for any tune that really uses 8 or 10 - which is most of
\ * them. A tune whose real envelope AKL could NOT encode gets a
\ * substitute on export and the pair has to be shifted back: Edge
\ * Grinder's EDGEA is envelope 12 throughout and needs ENV_BASE = 12.
\ *
\ * It is not defaulted here on purpose. It is a property of the SONG,
\ * not of the player, and a default is exactly how it came to be 12 -
\ * right for the one tune it was written for and wrong for every other.
\ * tools/arkos.py's envelope_base() reads the true shape out of an AKG
\ * source export and example/build.py passes it through; getting it
\ * wrong shows up as `env shape` in tools/verify/verify.py.
\ *
\ * tools/verify/akl_reference.py has its own copy and the two MUST
\ * agree, or the harness proves the player right against a reference
\ * with the same mistake in it.
\ ******************************************************************



\ ******************************************************************
\ * t_transp AFTER akl_init, IF THE EXPORT LOST POSITION 0's.
\ *
\ * AKL's linker encodes a transposition only when it CHANGES, and this
\ * player starts at zero - so a song whose FIRST position is transposed
\ * depends on AT2's exporter writing it there, and it does not always.
\ * Edge Grinder's WON4 needs (0, -3, -7) and the export carries nothing:
\ * 216 frames of notes in the wrong key, in tune with themselves, with
\ * nothing in the register stream to say so.
\ *
\ * akl_init clears t_transp and does NOT read the linker, and a first
\ * linker entry that sets no transposition leaves it alone - so the fix
\ * is three stores between akl_init and the first akl_play:
\ *
\ *     jsr akl_init
\ *     lda #0 : sta t_transp+0         \ what export_akl.py --check
\ *     lda #-3 : sta t_transp+1        \ prints for this song
\ *     lda #-7 : sta t_transp+2
\ *
\ * Proved on WON4: every audible period difference against Arkos's own
\ * replay goes, over all 3,312 frames. `python tools/export_akl.py
\ * <song> --check` reports the triple and refuses the export without it;
\ * example/build.py passes it through. See docs/format-akl.md.
\ ******************************************************************

\ ******************************************************************
\ * akl_init - A/X = LO/HI of the song, Y = subsong index
\ ******************************************************************
.akl_init
{
    sta tptr : stx tptr+1
    sty tmp

    \ song header: "ATLW", version, then the three table pointers
    ldy #5
    lda (tptr),y : sta inst_tbl
    iny
    lda (tptr),y : sta inst_tbl+1
    iny
    lda (tptr),y : sta arp_tbl
    iny
    lda (tptr),y : sta arp_tbl+1
    iny
    lda (tptr),y : sta pit_tbl
    iny
    lda (tptr),y : sta pit_tbl+1

    \ subsong pointer, at header + 11 + 2 * index
    lda tmp : asl a : clc : adc #11 : tay
    lda (tptr),y : sta ptr
    iny
    lda (tptr),y : sta ptr+1

    \ subsong header: the initial speed, then the linker
    ldy #0
    lda (ptr),y : sta akl_speed
    sec : sbc #1 : sta akl_tick         \ force a new line on the first play
    lda ptr   : clc : adc #1 : sta lnk
    lda ptr+1 : adc #0 : sta lnk+1

    \ clear the per-channel state
    lda #0
    sta akl_height : sta akl_prevh : sta r13 : sta r13_old
    ldx #(state_end - state_start - 1)
.clr
    sta state_start,x
    dex
    bpl clr

    \ every channel starts on the empty instrument, past its speed byte
    lda inst_tbl   : sta iptr
    lda inst_tbl+1 : sta iptr+1
    ldy #0
    lda (iptr),y : sta tptr
    iny
    lda (iptr),y : sta tptr+1
    lda tptr : clc : adc #1 : sta tptr
    lda tptr+1 : adc #0 : sta tptr+1
    ldx #2
.ins
    lda tptr   : sta t_inst_lo,x : sta t_base_lo,x
    lda tptr+1 : sta t_inst_hi,x : sta t_base_hi,x
    dex
    bpl ins
    rts
}

\ ******************************************************************
\ * akl_play - one frame. Fills ay_regs.
\ ******************************************************************
.akl_play
{
    inc akl_tick
    lda akl_tick
    cmp akl_speed
    bne no_new_line

    lda #0
    sta akl_tick
    lda akl_height
    bne dec_height
    jsr read_linker
    jmp read_lines
.dec_height
    dec akl_height
.read_lines
    ldx #0
.rl_loop
    jsr read_track
    inx
    cpx #3
    bne rl_loop

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
\ ******************************************************************
.read_linker
{
    lda lnk : sta ptr
    lda lnk+1 : sta ptr+1
.top
    lda #0
    sta t_wait+0 : sta t_wait+1 : sta t_wait+2

    ldy #0
    lda (ptr),y
    iny
    lsr a                       \ C = pattern present?
    bcs not_end

    \ end of song: the loop address follows
    lda (ptr),y : sta tmp
    iny
    lda (ptr),y : sta ptr+1
    lda tmp : sta ptr
    jmp top

.not_end
    sta cell                    \ the remaining flags, shifted down one
    lsr a                       \ C = new speed?
    bcc no_speed
    lda (ptr),y
    iny
    sta akl_speed
.no_speed
    lda cell
    lsr a : lsr a               \ C = new height?
    bcc no_height
    lda (ptr),y
    iny
    sta akl_prevh
.no_height
    lda akl_prevh
    sta akl_height

    lda cell
    lsr a : lsr a : lsr a       \ C = new transpositions?
    bcc no_transp
    lda (ptr),y : sta t_transp+0 : iny
    lda (ptr),y : sta t_transp+1 : iny
    lda (ptr),y : sta t_transp+2 : iny
.no_transp

    \ three track pointers
    lda (ptr),y : sta t_track_lo+0 : iny
    lda (ptr),y : sta t_track_hi+0 : iny
    lda (ptr),y : sta t_track_lo+1 : iny
    lda (ptr),y : sta t_track_hi+1 : iny
    lda (ptr),y : sta t_track_lo+2 : iny
    lda (ptr),y : sta t_track_hi+2 : iny

    tya
    clc : adc ptr : sta lnk
    lda ptr+1 : adc #0 : sta lnk+1
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
    lda (ptr),y
    iny
    sta cell
    and #&3f
    cmp #60
    bcc note                    \ 0-59: a note in octaves 2-6
    bne not_60                  \ 60: no note, effect
    jmp effect_only
.not_60
    cmp #61
    bne not_61
    jmp wait_long
.not_61
    cmp #62
    bne not_62
    jmp wait_short
.not_62
    \ 63: escape - the full note follows
    lda (ptr),y
    iny
    jmp have_note

.note
    clc
    adc #24                     \ octave compensation
.have_note
    clc
    adc t_transp,x
    sta t_base_note,x

    lda cell
    bpl same_inst

    \ new instrument: the byte is already the index * 2
    lda (ptr),y
    iny
    sty iofs
    clc
    adc inst_tbl : sta tptr
    lda inst_tbl+1 : adc #0 : sta tptr+1
    ldy #0
    lda (tptr),y : sta iptr
    iny
    lda (tptr),y : sta iptr+1
    ldy #0
    lda (iptr),y : sta t_inst_speed,x       \ the instrument's speed header
    lda iptr   : clc : adc #1 : sta t_inst_lo,x : sta t_base_lo,x
    lda iptr+1 : adc #0 : sta t_inst_hi,x : sta t_base_hi,x
    ldy iofs
    jmp after_inst

.same_inst
    lda t_base_lo,x : sta t_inst_lo,x
    lda t_base_hi,x : sta t_inst_hi,x
.after_inst
    lda #0
    sta t_inst_step,x
    sta t_pud,x                 \ the track pitch resets on a new note...
    sta t_pint_lo,x             \ ...but its decimal part deliberately does not
    sta t_pint_hi,x
    sta t_arp_off,x
    sta t_pit_off,x

    lda cell
    and #&40
    beq store
    jsr read_effect
.store
    tya
    clc : adc ptr : sta t_track_lo,x
    lda ptr+1 : adc #0 : sta t_track_hi,x
    rts

.effect_only
    jsr read_effect
    jmp store

.wait_long
    lda (ptr),y
    iny
    sta t_wait,x
    jmp store

.wait_short
    lda cell
    rol a : rol a : rol a
    and #3
    sta t_wait,x
    jmp store
}

\ ******************************************************************
\ * read_effect - X = channel, Y = offset into (ptr). Advances Y.
\ ******************************************************************
.read_effect
{
    lda (ptr),y
    iny
    sty iofs_e                                   \ Y is needed for the vector
    sta cell
    lsr a : lsr a : lsr a : lsr a : lsr a        \ effect number
    asl a
    tay                                          \ Y = number * 2
    lda fx_vec+0,y : sta jvec
    lda fx_vec+1,y : sta jvec+1
    ldy iofs_e
    jmp (jvec)                                   \ each handler ends in RTS

.fx_vec
    equw fx_reset
    equw fx_arp
    equw fx_pit
    equw fx_pud
    equw fx_vol_pud
    equw fx_vol_arp
    equw fx_reset_arp
    equw fx_bad
}
.iofs_e     skip 1

.fx_bad
    rts

.fx_reset
{
    lda cell
    and #&0f
    sta t_inv_vol,x
    jsr do_reset
    rts
}

.do_reset
{
    lda #0
    sta t_pud,x
    sta t_arp_used,x
    sta t_arp_val,x
    sta t_pit_used,x
    rts
}

.fx_arp
{
    lda cell
    and #&1f
    jsr set_arp
    rts
}

.fx_pit
{
    lda cell
    and #&1f
    jsr set_pit
    rts
}

.fx_pud
{
    lda cell
    lsr a
    bcs start_pud_j
    lda #0
    sta t_pud,x
    rts
.start_pud_j
    jmp start_pud
}

.fx_vol_pud
{
    lda cell
    and #&0f
    sta t_inv_vol,x
    lda cell
    and #&10
    beq done
    jmp start_pud
.done
    rts
}

.fx_vol_arp
{
    lda cell
    and #&0f
    sta t_inv_vol,x
    lda (ptr),y
    iny
    jsr set_arp
    rts
}

.fx_reset_arp
{
    lda cell
    and #&0f
    sta t_inv_vol,x
    jsr do_reset
    lda (ptr),y
    iny
    jsr set_arp
    rts
}

\ A = the 16-bit pitch speed follows at (ptr),y. Sign is bit 15; it is
\ split out here so the per-frame path never has to mask it.
.start_pud
{
    lda #255
    sta t_pud,x
    lda (ptr),y
    iny
    sta t_pspd_lo,x
    lda (ptr),y
    iny
    sta t_pspd_hi,x
    and #&80
    sta t_pneg,x
    lda t_pspd_hi,x
    and #&7f
    sta t_pspd_hi,x
    rts
}

\ A = arpeggio number
.set_arp
{
    sta t_arp_used,x
    bne start
    sta t_arp_val,x
    rts
.start
    sty iofs
    asl a
    clc : adc arp_tbl : sta tptr
    lda arp_tbl+1 : adc #0 : sta tptr+1
    ldy #0
    lda (tptr),y : sta t_arp_lo,x
    iny
    lda (tptr),y : sta t_arp_hi,x
    lda #0
    sta t_arp_off,x
    ldy iofs
    rts
}

\ A = pitch-table number
.set_pit
{
    sta t_pit_used,x
    beq out
    sty iofs
    asl a
    clc : adc pit_tbl : sta tptr
    lda pit_tbl+1 : adc #0 : sta tptr+1
    ldy #0
    lda (tptr),y : sta t_pit_lo,x
    iny
    lda (tptr),y : sta t_pit_hi,x
    lda #0
    sta t_pit_off,x
    ldy iofs
.out
    rts
}

\ ******************************************************************
\ * manage_effects - X = channel. The per-frame effect state.
\ ******************************************************************
.manage_effects
{
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

    lda t_arp_used,x
    beq no_arp
    lda t_arp_lo,x : sta tptr
    lda t_arp_hi,x : sta tptr+1
    ldy t_arp_off,x
.arp_again
    lda (tptr),y
    lsr a
    bcc arp_value
    \ end of the arpeggio: the loop offset is what is left in A
    sta t_arp_off,x
    tay
    jmp arp_again
.arp_value
    cmp #&40                    \ sign-extend the 7-bit value
    bcc arp_pos
    ora #&80
.arp_pos
    sta t_arp_val,x
    iny
    tya
    sta t_arp_off,x
.no_arp

    lda t_pit_used,x
    beq no_pit
    lda t_pit_lo,x : sta tptr
    lda t_pit_hi,x : sta tptr+1
    ldy t_pit_off,x
.pit_again
    lda (tptr),y
    lsr a
    bcc pit_value
    sta t_pit_off,x
    tay
    jmp pit_again
.pit_value
    ldy #0
    cmp #&40
    bcc pit_pos
    ora #&80
    ldy #&ff
.pit_pos
    sta t_pitv_lo,x
    tya
    sta t_pitv_hi,x
    ldy t_pit_off,x
    iny
    tya
    sta t_pit_off,x
.no_pit
    rts
}

\ ******************************************************************
\ * play_stream - X = channel. Walks the instrument, sets the channel's
\ * volume, period, and any noise / hardware registers.
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

    \ end of sound: loop to the address that follows
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
    bmi nsnh_noise
    jmp store_ptr
.nsnh_noise
    jsr read_noise
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
    lsr a
    cmp #&40
    bcc arp_pos
    ora #&80
.arp_pos
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
    \ hardware period = software period >> (7 - inverted ratio), rounded
    lda cell
    lsr a : lsr a : lsr a : lsr a
    and #7
    sta tmp
    lda #7
    sec : sbc tmp
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
    beq speed_reached
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
    lda (iptr),y
    iny
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
    and #&7f
    tay
    lda per_lo,y : sta per
    lda per_hi,y : sta per+1

    lda t_pit_used,x
    beq no_pit
    clc
    lda per   : adc t_pitv_lo,x : sta per
    lda per+1 : adc t_pitv_hi,x : sta per+1
.no_pit
    lda t_pud,x
    beq no_pud
    clc
    lda per   : adc t_pint_lo,x : sta per
    lda per+1 : adc t_pint_hi,x : sta per+1
.no_pud
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

\ The CPC period table, 128 notes, split into low and high bytes.
\ Generated from PlayerLightweight.asm's own table by tools-side Python.
INCLUDE "lib/akl_periods.asm"

.state_start
.t_wait         skip 3
.t_transp       skip 3
.t_base_note    skip 3
.t_inst_step    skip 3
.t_inst_speed   skip 3
.t_inv_vol      skip 3
.t_track_lo     skip 3
.t_track_hi     skip 3
.t_inst_lo      skip 3
.t_inst_hi      skip 3
.t_base_lo      skip 3
.t_base_hi      skip 3
.t_pud          skip 3
.t_pneg         skip 3
.t_pdec         skip 3
.t_pspd_lo      skip 3
.t_pspd_hi      skip 3
.t_pint_lo      skip 3
.t_pint_hi      skip 3
.t_arp_used     skip 3
.t_arp_off      skip 3
.t_arp_val      skip 3
.t_arp_lo       skip 3
.t_arp_hi       skip 3
.t_pit_used     skip 3
.t_pit_off      skip 3
.t_pitv_lo      skip 3
.t_pitv_hi      skip 3
.t_pit_lo       skip 3
.t_pit_hi       skip 3
.chan_vol       skip 3
.chan_per_lo    skip 3
.chan_per_hi    skip 3
.noise_reg      skip 1
.reg11          skip 1
.reg12          skip 1
.r13            skip 1
.r13_old        skip 1
.state_end

.inst_tbl       skip 2
.arp_tbl        skip 2
.pit_tbl        skip 2

\ ay_regs itself lives in lib/ay2sn.asm - it is the library's boundary
\ and every player in this repo fills the same fourteen bytes.
.akl_end
