\ ******************************************************************
\ * ay2sn.asm - the runtime AY-3-8912 -> SN76489 layer, for measurement
\ *
\ * The offline chain (ym2sn.py) does this once, with whole-song
\ * analysis. A tracker replay on the BBC has to do it every frame.
\ * This is what that costs.
\ *
\ * Tone:   the CPC AY runs at 1 MHz and the SN at 4 MHz, so
\ *         SN period = 2 * AY period exactly - ym2sn's own formula
\ *         reduces to that. Periods over ten bits are halved until
\ *         they fit, which is the octave-up ym2sn does as well.
\ * Volume: AY 4-bit volume -> 5-bit -> a 32-entry attenuation LUT,
\ *         the same mapping ym2sn builds.
\ * Noise:  AY 5-bit noise period -> one of the SN's three rates.
\ * Envelope: there is ONE envelope generator on the AY, so one phase
\ *         accumulator. It is SAMPLED once a frame, not averaged over
\ *         the frame the way ym2sn does. That is the cheap option and
\ *         it is audibly not the same thing - see the report.
\ ******************************************************************

.ay2sn
{
    \ ---- the envelope generator, once for all three channels -------
    lda ay_regs+12
    bne slow_env                \ period >= 256: a step under 20000, rare
    ldy ay_regs+11
    lda env_recip_lo,y : sta env_step
    lda env_recip_hi,y : sta env_step+1
    jmp got_step
.slow_env
    lda #0    : sta env_step
    lda #&40  : sta env_step+1
.got_step
    clc
    lda env_phase   : adc env_step   : sta env_phase
    lda env_phase+1 : adc env_step+1 : sta env_phase+1
    lsr a : lsr a : lsr a       \ the 32-step envelope position
    tay
    lda env_shape,y
    sta env_level

    lda #15                     \ nothing has the noise open yet
    sta noise_att

    ldx #0
.ch_loop
    \ ---- volume ----------------------------------------------------
    lda ay_regs+8,x
    and #16
    beq fixed_vol
    lda env_level
    jmp have_vol5
.fixed_vol
    lda ay_regs+8,x
    and #15
    asl a
    ora #1                      \ 4-bit volume -> the 5-bit scale
.have_vol5
    tay
    lda ym_sn_vol,y
    sta att

    \ ---- does this channel have the noise open? --------------------
    \ If so its volume is the drum's, and it is taken HERE, before the
    \ tone-disable test below: on the AY a channel with the tone off and
    \ the noise on still plays the noise at its own volume. The loudest
    \ such channel wins, so lower attenuation replaces higher.
    lda ay_regs+7
    and noise_bit,x
    bne not_noise_ch
    lda att
    cmp noise_att
    bcs not_noise_ch
    sta noise_att
.not_noise_ch

    \ ---- tone disabled? then the channel is silent -----------------
    lda ay_regs+7
    and tone_bit,x
    beq tone_on
    lda #15
    sta att
.tone_on

    \ ---- period: SN = AY * 2, halved until it fits ten bits --------
    ldy per_idx,x
    lda ay_regs,y
    asl a
    sta snper
    lda ay_regs+1,y
    and #15
    rol a
    sta snper+1
.fit
    lda snper+1
    cmp #4
    bcc fits
    lsr snper+1
    ror snper
    jmp fit
.fits
    lda snper
    ora snper+1
    bne nonzero
    inc snper                   \ never write a period of zero
.nonzero

    \ ---- park this channel's SN bytes; the writes come after the loop
    lda snper
    and #15
    ora sn_tone_latch,x
    sta sn_t0,x
    lda snper+1
    asl a : asl a : asl a : asl a
    sta tmp2
    lda snper
    lsr a : lsr a : lsr a : lsr a
    ora tmp2
    sta sn_t1,x
    lda att
    ora sn_vol_latch,x
    sta sn_v,x

    inx
    cpx #3
    beq chans_done
    jmp ch_loop
.chans_done
    \ ---- the nine tone/volume writes, X now free for sn_write -----
    lda sn_t0+0 : jsr sn_write
    lda sn_t1+0 : jsr sn_write
    lda sn_v+0  : jsr sn_write
    lda sn_t0+1 : jsr sn_write
    lda sn_t1+1 : jsr sn_write
    lda sn_v+1  : jsr sn_write
    lda sn_t0+2 : jsr sn_write
    lda sn_t1+2 : jsr sn_write
    lda sn_v+2  : jsr sn_write

    \ ---- noise -----------------------------------------------------
    \ &E4, not &E0: bit 2 of the noise byte is the FEEDBACK bit, and it
    \ selects WHITE noise. With it clear the SN plays PERIODIC noise, which
    \ is a pitched buzz, not a drum - every percussion hit came out as a
    \ spurious tone (KC heard it). Bits 0-1 are the rate.
    lda ay_regs+7
    and #&38
    cmp #&38
    beq no_noise
    lda ay_regs+6
    and #31
    tay
    lda ay_noise_rate,y
    ora #&e4
    cmp noise_last
    beq noise_same
    sta noise_last
    jsr sn_write
.noise_same
    \ The drum's loudness is the volume of whichever AY channel has the
    \ noise open - the channel loop parked the loudest in noise_att. It
    \ used to be hard-coded to full, so every hit was flat out.
    lda noise_att
    ora #&f0
    jmp sn_write
.no_noise
    lda #&ff                    \ channel 3 silent
    jmp sn_write
}

\ One byte to the SN76489. Lifted verbatim from lib/vgiplayer.asm -
\ it drives the System VIA and the addressable latch, and it uses X.
.sn_write
{
    ldx #255
    stx &fe43
    sta &fe4f
    inx
    stx &fe40
    lda &fe40
    ora #8
    sta &fe40
    rts
}

.ay_regs      skip 14   \ THE BOUNDARY: the AY-3-8912 register file that
                          \ every player in this library fills, and that
                          \ ay2sn converts. R0-R13, in AY order.

.att          skip 1
.snper        skip 2
.tmp2         skip 1
.noise_last   skip 1
.noise_att    skip 1        \ the drum's attenuation this frame
.sn_t0        skip 3
.sn_t1        skip 3
.sn_v         skip 3
.env_phase    skip 2
.env_step     skip 2
.env_level    skip 1

.per_idx        equb 0, 2, 4
.sn_tone_latch  equb &80, &a0, &c0
.sn_vol_latch   equb &90, &b0, &d0
.noise_bit      equb 8, 16, 32      \ R7's noise-disable bit, per channel
.tone_bit       equb 1, 2, 4        \ R7's tone-disable bit; the players
                                    \ use it too, so it lives on the spine

INCLUDE "lib/ay2sn_tables.asm"

\ ******************************************************************
\ * akl_silence - the four volume-off writes, for Q's mute.
\ ******************************************************************
\ *	Byte-identical in effect to lib/vgiplayer.asm's sn_reset, which is
\ *	what the VGI build calls. Q mutes by running THIS INSTEAD OF a
\ *	frame of music, never as well as - see BUGS.md #11: letting the
\ *	player run and silencing the chip after it puts a 123 us burst of
\ *	the tune's own volumes out fifty times a second, and crackles.
\ ******************************************************************

.akl_silence
{
    lda #&9f : jsr sn_write
    lda #&bf : jsr sn_write
    lda #&df : jsr sn_write
    lda #&ff : jmp sn_write
}
