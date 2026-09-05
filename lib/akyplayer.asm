\ ******************************************************************
\ * akyplayer.asm - Arkos Tracker AKY replay, 6502, for the BBC Micro
\ *
\ * A port of Krzysztof Dudek's (xxl) Atari 8-bit AKY player, which is
\ * itself a 6502 conversion of Targhan/Arkos's Z80 AKY player. Both
\ * are MIT; see LICENSES/ and reference/PlayerAky_atari_mads.asm, which
\ * is the source this was converted from, kept unmodified beside it.
\ *
\ * WHAT CHANGED, and only this:
\ *
\ *   1. MADS syntax -> BeebASM. The anonymous `@` labels are named.
\ *   2. The Atari writes each register to a real AY as it computes it:
\ *          lda #reg : sta AYR   /   lda value : sta AYD
\ *      The BBC has no AY. Every such pair becomes a write into
\ *      ay_regs, this library's boundary - `sta ay_sel` then
\ *      `jsr ay_put`. lib/ay2sn.asm turns the fourteen bytes into
\ *      SN76489 writes once the frame is complete.
\ *
\ * Nothing else is touched. The decode is byte for byte the Atari's,
\ * which is why it can be checked against Arkos's own player output.
\ *
\ * Conventions inherited from the Atari source:
\ *   X = channel, 0-2, through the whole of a block's processing.
\ *   Y = byte offset into the register block being read.
\ *
\ * COST: ay_put is ~19 cycles a register write, against the Atari's 8.
\ * That is the price of being mechanically faithful, and it is paid on
\ * maybe a dozen writes a frame. Fold the register number into a direct
\ * store per site if it ever matters - but verify it afterwards.
\ ******************************************************************

\ ******************************************************************
\ * aky_init - A/X = lo/hi of the AKY FILE (its header, not the linker)
\ *
\ * The Atari player is handed the linker directly and ignores the
\ * header, because its songs come from a source export with labels.
\ * A binary export has no labels, so this parses the header instead:
\ * one flags byte, one channel count, then a four-byte PSG frequency
\ * PER PSG. Getting that offset wrong does not fail - the player reads
\ * the frequency as a linker entry and plays convincing silence.
\ *
\ * The channel count also gives the linker's STRIDE. A linker entry is
\ * a duration word and then one track pointer per channel, so a
\ * six-channel song's entries are 14 bytes where a three-channel
\ * song's are 8. Reading the first three pointers and stepping by the
\ * full stride plays the FIRST PSG of a multi-PSG song and ignores the
\ * rest - which is what you want when the other channels are not music
\ * (Arkos songs sometimes carry event data on a second PSG), and is
\ * the only thing a one-chip machine can do in any case.
\ ******************************************************************
.aky_init
{
    sta aky_block : stx aky_block+1

    ldy #1
    lda (aky_block),y               \ channel count: three per PSG
    ldx #0
.count_psgs
    cmp #3
    bcc counted
    sbc #3                          \ carry is set: A >= 3
    inx
    bne count_psgs                  \ always
.counted
    txa                             \ X = PSGs
    asl a                           \ 2 * PSGs
    sta aky_stride
    asl a                           \ 4 * PSGs = the frequency bytes
    pha                             \ ...which is the header, less two
    clc
    adc aky_stride                  \ 6 * PSGs = the pointer bytes
    adc #2                          \ + the duration word = the stride
    sta aky_stride

    pla                             \ the header length, less its two
    clc                             \ leading bytes
    adc #2
    clc
    adc aky_block   : sta aky_linker
    lda aky_block+1 : adc #0 : sta aky_linker+1

    ldx #1
    stx aky_c1_state
    stx aky_c2_state
    stx aky_c3_state
    stx aky_patfc
    dex
    stx aky_patfc+1
    rts
}

\ ******************************************************************
\ * ay_put - A -> ay_regs[ay_sel]. Preserves A and X.
\ *
\ * This is the whole of the hardware layer. The Atari's `sta AYD`
\ * became a call to this, and nothing else in the player knows what
\ * machine it is on.
\ ******************************************************************
.ay_put
{
    stx ay_xtmp
    ldx ay_sel
    sta ay_regs,x
    ldx ay_xtmp
    rts
}
.ay_sel     skip 1
.ay_xtmp    skip 1

\ ******************************************************************
\ * aky_play - one frame. Fills ay_regs.
\ ******************************************************************
.aky_play
{
    lda aky_patfc
    bne dec_lo
    dec aky_patfc+1
.dec_lo
    dec aky_patfc
    bne not_over
    ldy aky_patfc+1
    beq pat_over
.not_over
    jmp chan1_wait

.pat_over
    \ New pattern: read the linker. Y is 0 here.
.linker_read
    lda (aky_linker),y
    sta aky_patfc
    iny
    lda (aky_linker),y
    sta aky_patfc+1
    ora aky_patfc
    bne linker_not_end

    \ 0000 = end of song: the next word is where to loop to.
    iny
    lda (aky_linker),y
    tax
    iny
    lda (aky_linker),y
    sta aky_linker+1
    stx aky_linker
    ldy #0
    beq linker_read                 \ always

.linker_not_end
    \ Six bytes: the three track pointers, into aky_c1_track onwards.
.lk_loop
    iny
    lda (aky_linker),y
    sta aky_c1_track-2,y
    cpy #7
    bcc lk_loop

    \ Step by the WHOLE entry, which for a multi-PSG song is longer
    \ than the three pointers just read - see aky_init.
    lda aky_linker
    clc
    adc aky_stride
    sta aky_linker
    bcc lk_done
    inc aky_linker+1
.lk_done

    lda #1
    sta aky_c1_wait
    sta aky_c2_wait
    sta aky_c3_wait

\ ---- each channel: is its next register block due? -----------------
.chan1_wait
    dec aky_c1_wait
    bne chan1_done
    lda #1                          \ carry set: an INITIAL state follows
    sta aky_c1_state
    ldy #0
.c1_copy
    lda (aky_c1_track),y
    sta aky_c1_wait,y
    iny
    cpy #3
    bcc c1_copy
    lda #2                          \ carry is set, so this adds 3
    adc aky_c1_track
    sta aky_c1_track
    bcc chan1_done
    inc aky_c1_track+1
.chan1_done

    dec aky_c2_wait
    bne chan2_done
    lda #1
    sta aky_c2_state
    ldy #0
.c2_copy
    lda (aky_c2_track),y
    sta aky_c2_wait,y
    iny
    cpy #3
    bcc c2_copy
    lda #2
    adc aky_c2_track
    sta aky_c2_track
    bcc chan2_done
    inc aky_c2_track+1
.chan2_done

    dec aky_c3_wait
    bne chan3_done
    lda #1
    sta aky_c3_state
    ldy #0
.c3_copy
    lda (aky_c3_track),y
    sta aky_c3_wait,y
    iny
    cpy #3
    bcc c3_copy
    lda #2
    adc aky_c3_track
    sta aky_c3_track
    bcc chan3_done
    inc aky_c3_track+1
.chan3_done

\ ---- read the three register blocks --------------------------------
    lda #&38                        \ all three tones on, all noise off
    sta aky_mixer

    ldx #0
    ldy #0
    lsr aky_c1_state
    jsr aky_read_block
    tya
    clc
    adc aky_block
    sta aky_c1_prb
    lda aky_block+1
    adc #0
    sta aky_c1_prb+1

    inx
    ldy #3
    lsr aky_c2_state
    jsr aky_read_block
    tya
    clc
    adc aky_block
    sta aky_c2_prb
    lda aky_block+1
    adc #0
    sta aky_c2_prb+1

    inx
    ldy #6
    lsr aky_c3_state
    jsr aky_read_block
    tya
    clc
    adc aky_block
    sta aky_c3_prb
    lda aky_block+1
    adc #0
    sta aky_c3_prb+1

\ ---- the registers the channels do not write themselves ------------
    lda aky_mixer       : sta ay_regs+7
    lda aky_noise       : sta ay_regs+6
    lda aky_envper      : sta ay_regs+11
    lda aky_envper+1    : sta ay_regs+12

    \ R13 is re-sent only when it changes - a retrig forces that by
    \ setting bit 7 of the old copy. 255 means "not sent this frame",
    \ the same convention lib/aklplayer.asm uses.
    lda aky_envshape
    cmp aky_envshape_old
    beq r13_same
    sta aky_envshape_old
    sta ay_regs+13
    rts
.r13_same
    lda #255
    sta ay_regs+13
    rts
}

\ ******************************************************************
\ * aky_read_block - X = channel, Y = 0/3/6, carry = initial state
\ ******************************************************************
.aky_read_block
{
    lda aky_c1_prb,y
    sta aky_block
    lda aky_c1_prb+1,y
    sta aky_block+1
    ldy #0
    lda (aky_block),y
    \ type: 00 no soft no hard, 01 software, 10 hardware, 11 both
    iny

    bcs initial
    jmp non_initial
.initial
    lsr a
    bcs is_soft_or_softhard
    lsr a
    bcs is_hard_only

\ ---- initial state, no software no hardware ------------------------
\ 7  6 5 4 3  2  1 0
\ 0  v v v v  n  t t
.is_nsnh
    lsr a
    pha
    bcc is_nsnh_vol
    lda (aky_block),y
    sta aky_noise
    iny
    lda aky_noise_off,x
    and aky_mixer
    sta aky_mixer
.is_nsnh_vol
    lda aky_amp,x
    sta ay_sel
    pla
    jsr ay_put
    lda aky_tone_on,x
    ora aky_mixer
    sta aky_mixer
    rts

\ ---- initial state, hardware only ----------------------------------
\ 7 6 5 4  3  2  1 0
\ e e e e  n  r  t t
.is_hard_only
    lsr a
    bcc is_ho_noretrig
    ror aky_envshape_old            \ carry is set: force a re-send
.is_ho_noretrig
    lsr a
    pha
    bcc is_ho_nonoise
    lda (aky_block),y
    sta aky_noise
    iny
    lda aky_noise_off,x
    and aky_mixer
    sta aky_mixer
.is_ho_nonoise
    pla
    sta aky_envshape
    lda (aky_block),y
    sta aky_envper
    iny
    lda (aky_block),y
    sta aky_envper+1
    iny
    lda aky_tone_on,x
    ora aky_mixer
    sta aky_mixer

    lda aky_amp,x
    sta ay_sel
    lda #&10
    jsr ay_put
    rts

.is_soft_or_softhard
    lsr a
    bcs is_soft_and_hard

\ ---- initial state, software only ----------------------------------
\ 7  6 5 4 3  2  1 0
\ 0  v v v v  n  t t
.is_soft_only
    lsr a
    pha
    bcc is_so_nonoise
    lda (aky_block),y
    sta aky_noise
    iny
    lda aky_noise_off,x
    and aky_mixer
    sta aky_mixer
.is_so_nonoise
    lda aky_amp,x
    sta ay_sel
    pla
    jsr ay_put

    lda aky_tone_lo,x
    sta ay_sel
    lda (aky_block),y
    jsr ay_put
    iny
    lda aky_tone_hi,x
    sta ay_sel
    lda (aky_block),y
    jsr ay_put
    iny
    rts

\ ---- initial state, software and hardware --------------------------
\ 7 6 5 4  3  2  1 0
\ e e e e  n  r  t t
.is_soft_and_hard
    lsr a
    bcc is_sah_noretrig
    ror aky_envshape_old
.is_sah_noretrig
    lsr a
    pha
    bcc is_sah_nonoise
    lda (aky_block),y
    sta aky_noise
    iny
    lda aky_noise_off,x
    and aky_mixer
    sta aky_mixer
.is_sah_nonoise
    pla
    sta aky_envshape
    lda aky_tone_lo,x
    sta ay_sel
    lda (aky_block),y
    jsr ay_put
    iny
    lda aky_tone_hi,x
    sta ay_sel
    lda (aky_block),y
    jsr ay_put
    iny
    lda aky_amp,x
    sta ay_sel
    lda #&10
    jsr ay_put
    lda (aky_block),y
    sta aky_envper
    iny
    lda (aky_block),y
    sta aky_envper+1
    iny
    rts

\ ---- a loop: follow the pointer and re-read -------------------------
.nis_loop
    lda (aky_block),y
    pha
    iny
    lda (aky_block),y
    sta aky_block+1
    pla
    sta aky_block
    ldy #0
    lda (aky_block),y
    iny

\ ---- non-initial state ---------------------------------------------
.non_initial
    lsr a
    bcs nis_soft_or_softhard
    lsr a
    bcc nis_nsnh_or_loop
    jmp nis_hard_only

\ 7  6 5 4 3 2  1 0
\ n  v v v v v  0 0     (v = new volume?; if not, bit 2 = loop)
.nis_nsnh_or_loop
    sta aky_token
    and #3
    cmp #2                          \ %10 = loop
    beq nis_loop

    lda aky_tone_on,x
    ora aky_mixer
    sta aky_mixer
    lsr aky_token
    bcc nis_novol
    lda aky_amp,x
    sta ay_sel
    lda aky_token
    and #&0f
    jsr ay_put
.nis_novol
    lda aky_token
    and #%00010000
    bne nis_nsnh_noise
    rts
.nis_nsnh_noise
    lda (aky_block),y
    sta aky_noise
    iny
    lda aky_noise_off,x
    and aky_mixer
    sta aky_mixer
    rts

.nis_soft_or_softhard
    lsr a
    bcc nis_soft_only
    jmp nis_soft_and_hard

\ ---- non-initial, software only ------------------------------------
\ 7         6    5 4 3 2  1 0
\ mspnoise  lsp  v v v v  0 1
.nis_soft_only
    sta aky_token
    lda aky_amp,x
    sta ay_sel
    lda aky_token
    and #&0f
    jsr ay_put

    lda aky_token
    and #%00010000
    beq nis_so_nolsp

    lda aky_tone_lo,x
    sta ay_sel
    lda (aky_block),y
    jsr ay_put
    iny

.nis_so_nolsp
    lda aky_token
    and #%00100000
    bne nis_so_msp
    rts
.nis_so_msp
    \ 7 6 5 4  3 2 1 0
    \ i n      p p p p     i = is noise?  n = new noise?  p = period MSB
    lda aky_tone_hi,x
    sta ay_sel
    lda (aky_block),y
    iny
    jsr ay_put

    asl a
    bcs nis_so_isnoise
    rts
.nis_so_isnoise
    asl a
    lda aky_noise_off,x
    and aky_mixer
    sta aky_mixer
    bcs nis_so_newnoise
    rts
.nis_so_newnoise
    lda (aky_block),y
    sta aky_noise
    iny
    rts

\ ---- non-initial, hardware only ------------------------------------
\ 7    6    5   4 3 2  1 0
\ lsp  msp  nr  e e e  1 0
.nis_hard_only
    asl a
    sta aky_envshape
    pha
    lda aky_tone_on,x
    ora aky_mixer
    sta aky_mixer
    lda aky_amp,x
    sta ay_sel
    lda #&10
    jsr ay_put

    pla
    asl a
    asl a
    sta aky_token
    bcc nis_ho_nolsb
    lda (aky_block),y
    sta aky_envper
    iny
.nis_ho_nolsb
    asl aky_token
    bcc nis_ho_nomsb
    lda (aky_block),y
    sta aky_envper+1
    iny
.nis_ho_nomsb
    asl aky_token
    bcs nis_noise_or_retrig
    rts

\ ---- non-initial, software and hardware ----------------------------
\ 7   6   5     4     3     2     1 0
\ rn  ne  mssp  lssp  mshp  lshp  1 1
.nis_soft_and_hard
    sta aky_token
    lda aky_amp,x
    sta ay_sel
    lda #&10
    jsr ay_put
    lsr aky_token
    bcc nis_sah_no_lsbh
    lda (aky_block),y
    sta aky_envper
    iny
.nis_sah_no_lsbh
    lsr aky_token
    bcc nis_sah_no_msbh
    lda (aky_block),y
    sta aky_envper+1
    iny
.nis_sah_no_msbh
    lsr aky_token
    bcc nis_sah_no_lsbs
    lda aky_tone_lo,x
    sta ay_sel
    lda (aky_block),y
    jsr ay_put
    iny
.nis_sah_no_lsbs
    lsr aky_token
    bcc nis_sah_no_msbs
    lda aky_tone_hi,x
    sta ay_sel
    lda (aky_block),y
    jsr ay_put
    iny
.nis_sah_no_msbs
    lsr aky_token
    bcc nis_sah_no_env
    lda (aky_block),y
    sta aky_envshape
    iny
.nis_sah_no_env
    lsr aky_token
    bcs nis_noise_or_retrig
    rts

\ ---- shared tail: noise and/or retrig ------------------------------
\ 7 6 5 4 3  2  1  0
\ o o o o o  n  i  r
.nis_noise_or_retrig
    lda (aky_block),y
    iny
    lsr a
    bcc nor_noretrig
    ror aky_envshape_old            \ carry is set: force a re-send
.nor_noretrig
    lsr a
    bcs nor_isnoise
    rts
.nor_isnoise
    pha
    lda aky_noise_off,x
    and aky_mixer
    sta aky_mixer
    pla
    lsr a
    bcs nor_newnoise
    rts
.nor_newnoise
    sta aky_noise
    rts
}

\ ******************************************************************
\ * state and tables
\ ******************************************************************
.aky_noise          skip 1
.aky_envper         skip 2
.aky_envshape       skip 1
.aky_envshape_old   skip 1
.aky_mixer          skip 1
.aky_stride         skip 1   \ bytes per linker entry; aky_init works it out

.aky_tone_lo    equb 0, 2, 4        \ AY register numbers, per channel
.aky_tone_hi    equb 1, 3, 5
.aky_amp        equb 8, 9, 10
.aky_tone_on    equb &01, &02, &04  \ OR into the mixer to ENABLE the tone
.aky_noise_off  equb &f7, &ef, &df  \ AND into the mixer to ENABLE the noise
.aky_end
