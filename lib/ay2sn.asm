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

\ A complete sweep of the AY's 5-bit envelope ladder averages 0.1961 of
\ full amplitude - level 12, which ym_sn_vol maps to SN attenuation 7.
ENV_MEAN_LEVEL  = 12

\ The envelope completes a whole cycle within one 50 Hz call when its
\ period is 78 or less: 5120000 / 78 > 65536, one full turn of the phase.
ENV_FULL_PERIOD = 78

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

    \ ...but a single sample is only the right answer for a SLOW envelope.
    \ Every envelope in EDGEA runs 1.17 to 2.89 complete cycles per call,
    \ so what the ear gets is the MEAN of the ramp while we emit whichever
    \ point we happened to land on - which is why envelope frames agreed
    \ with the offline chain on 3.6% of tone periods. A full sweep of the
    \ AY's 5-bit ladder averages 0.1961 of full amplitude, which is level
    \ ENV_MEAN_LEVEL. See docs/fidelity-plan.md.
        \ The threshold is on the envelope PERIOD because env_step is the
    \ phase increment modulo one cycle and cannot tell you how many whole
    \ cycles went by. Both it and env_recip assume the player is called
    \ 50 times a second; a 25 Hz host must double both.
    lda ay_regs+12
    bne env_slow                \ period >= 256: far slower than a call
    lda ay_regs+11
    cmp #ENV_FULL_PERIOD + 1
    bcs env_slow
    lda #ENV_MEAN_LEVEL
    sta env_level
.env_slow

    lda #15                     \ nothing has the noise open yet
    sta noise_att
    lda #255                    \ and no channel has claimed the bass
    sta bass_chan

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

    \ Too low for the chip? The SN's period is ten bits, so its lowest
    \ note is 122 Hz and the loop below would shift anything under that up
    \ an octave. If a software bass voice is free, take it instead.
    lda snper+1
    cmp #4
    bcc fit                     \ it fits: nothing to do here
    lda bass_enable
    beq fit                     \ no timer wired up: octave-shift as before
    lda bass_chan
    bpl fit                     \ the one voice is already taken this call
    jsr bass_claim
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
    \ The bass channel's VOLUME is the interrupt's to write - it is the
    \ square wave - so this must not stamp on it once a call.
    lda sn_t0+0 : jsr sn_write
    lda sn_t1+0 : jsr sn_write
    lda bass_chan : beq no_v0
    lda sn_v+0  : jsr sn_write
.no_v0
    lda sn_t0+1 : jsr sn_write
    lda sn_t1+1 : jsr sn_write
    lda bass_chan : cmp #1 : beq no_v1
    lda sn_v+1  : jsr sn_write
.no_v1
    lda sn_t0+2 : jsr sn_write
    lda sn_t1+2 : jsr sn_write
    lda bass_chan : cmp #2 : beq no_v2
    lda sn_v+2  : jsr sn_write
.no_v2

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
    jsr sn_write
    jmp bass_update
.no_noise
    lda #&ff                    \ channel 3 silent
    jsr sn_write
    jmp bass_update
}

\ ******************************************************************
\ * The software bass voice
\ *
\ * The SN's period is ten bits, so its lowest note is 122 Hz. Anything
\ * below that used to be shifted up an octave, which is between a third
\ * and nearly half of every tune measured.
\ *
\ * Instead: park the channel's TONE at period 1 - a 125 kHz carrier,
\ * inaudible, and the BBC's analog chain filters it out anyway - and let
\ * a VIA timer toggle that channel's ATTENUATION between the note's
\ * volume and silence at the note's own frequency. The square wave is
\ * generated in the volume domain. The technique is Simon Morris's, from
\ * vgcplayer_bass.asm in vgm-player-bbc.
\ *
\ * It costs no musical channel - the drums and the other two tones are
\ * untouched - which is what makes it better than the periodic-noise
\ * alternative. It costs a timer and two interrupts per cycle: 102 to
\ * 157 a second on the tunes measured, about 0.5% of the CPU.
\ *
\ * ONE voice. That is enough for every frame of Rhino's Acid Demo, 83%
\ * of Dead On Time and 91% of EDGEA; the rest octave-shift as before.
\ *
\ * TO USE IT the host must:
\ *   1. put User VIA T1 in FREE-RUN mode (ACR bit 6 set, bit 7 clear),
\ *      so it reloads itself and the interrupt only has to toggle;
\ *   2. call bass_irq when User VIA T1 interrupts (IFR bit 6);
\ *   3. set bass_enable to 1.
\ * Leave bass_enable at 0 and none of this runs - the octave shift stays.
\ *
\ * The bass is only as steady as the interrupt latency, so a host that
\ * disables interrupts for long stretches will hear the pitch wobble.
\ ******************************************************************

USR_T1CL = &FE64        \ counter, low  - reading it clears the interrupt
USR_T1CH = &FE65        \ counter, high - writing it starts the timer
USR_T1LL = &FE66        \ latch, low    - the period of the NEXT cycle...
USR_T1LH = &FE67        \ latch, high   - ...without restarting this one
USR_IER  = &FE6E

\ ******************************************************************
\ * bass_claim - X = channel, snper = 2 * the AY period. Called from the
\ * channel loop when the note is below the chip's floor.
\ ******************************************************************
.bass_claim
{
    stx bass_chan

    \ The timer counts microseconds and wants HALF a period. An AY period
    \ p sounds at 1000000 / (16 * p) Hz, so half a period is 8 * p us -
    \ and snper is already 2 * p. The VIA counts (N + 2), so N = 4 * snper - 2.
    lda snper   : asl a : sta bass_n
    lda snper+1 : rol a : sta bass_n+1
    asl bass_n  : rol bass_n+1
    lda bass_n   : sec : sbc #2 : sta bass_n
    lda bass_n+1 : sbc #0 : sta bass_n+1

    \ the two bytes the interrupt alternates between
    lda sn_vol_latch,x : ora att  : sta bass_on
    lda sn_vol_latch,x : ora #15  : sta bass_off

    \ and the inaudible carrier
    lda #1 : sta snper
    lda #0 : sta snper+1
    rts
}

\ ******************************************************************
\ * bass_update - start, retune or stop the timer. Ends the frame.
\ ******************************************************************
.bass_update
{
    lda bass_chan
    bpl playing

    \ Nothing wants the bass. Stop the timer if it was running, and put
    \ the channel's own volume back - the interrupt may have left it
    \ silent, and nothing else writes it while the bass owns it.
    lda bass_running
    beq done
    lda #0   : sta bass_running
    lda #&FF : sta bass_last        \ force a retune when it comes back
    lda #&40 : sta USR_IER          \ bit 7 clear = disable T1
    lda bass_off
    and #&F0                        \ the same channel, volume 0 = loudest
    jmp sn_write

.playing
    \ Retune ONLY when the note has actually changed. Free-run reloads
    \ from the latches by itself, and writing them every call - even with
    \ the same value - pulls the timer's phase towards the call rate:
    \ measured, one bass edge landed at exactly the same offset into
    \ every single frame instead of drifting freely across it.
    lda bass_n
    cmp bass_last
    bne retune
    lda bass_n+1
    cmp bass_last+1
    beq no_retune
.retune
    lda bass_n   : sta USR_T1LL : sta bass_last
    lda bass_n+1 : sta USR_T1LH : sta bass_last+1
.no_retune

    lda bass_running
    bne done
    lda #1 : sta bass_running
    lda bass_n   : sta USR_T1CL     \ and start it
    lda bass_n+1 : sta USR_T1CH
    lda #&C0 : sta USR_IER          \ bit 7 set = enable T1
.done
    rts
}

\ ******************************************************************
\ * bass_irq - call this when User VIA T1 interrupts. Half a cycle of
\ * the bass square wave. Uses A only.
\ ******************************************************************
.bass_irq
{
    lda USR_T1CL                    \ reading the counter clears the flag
    txa : pha                       \ sn_write uses X
    lda bass_phase
    eor #1
    sta bass_phase
    bne send
    lda bass_off
    jmp out
.send
    lda bass_on
.out
    jsr sn_write
    pla : tax
    rts
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

.bass_enable  skip 1        \ 0 = octave-shift as before; the host sets it
.bass_chan    skip 1        \ 0-2 while a voice is claimed, 255 otherwise
.bass_running skip 1        \ is the timer going?
.bass_phase   skip 1        \ which half of the square wave is next
.bass_on      skip 1        \ the channel's volume byte, sounding...
.bass_off     skip 1        \ ...and silent
.bass_n       skip 2        \ the timer count: half a period, in us
.bass_last    skip 2        \ what the timer was last actually given

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
