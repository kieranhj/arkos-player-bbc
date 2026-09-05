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
\ * Volume: AY 4-bit volume -> 5-bit by duplicating the low bit -> a
\ *         32-entry attenuation LUT. Both halves are ym2sn's DEFAULT
\ *         settings, not its dB-faithful -t option; see make_tables.py.
\ * Noise:  AY 5-bit noise period -> the nearest of the SN's three fixed
\ *         rates by frequency, which is ym2sn's choice. The fourth rate
\ *         clocks the noise from tone generator 3 and is never a drum:
\ *         it is the periodic-noise bass, bass_mode 2 below.
\ * Envelope: there is ONE envelope generator on the AY, so one phase
\ *         accumulator. It is SAMPLED once a frame, not averaged over
\ *         the frame the way ym2sn does. That is the cheap option and
\ *         it is audibly not the same thing - see the report.
\ *
\ * TWO THINGS THE HOST HAS TO KNOW:
\ *
\ * 1. CALL THIS WITH INTERRUPTS OFF, or from an interrupt handler.
\ *    DDRA is set ONCE on entry and every SN write after that relies on
\ *    it still being set, so nothing that changes DDRA may run in the
\ *    middle - and the MOS's own 100 Hz keyboard scan does. A VSync IRQ
\ *    handler already has the I flag set and needs nothing; anywhere
\ *    else, wrap the call in sei/cli. It is worth ~60 cycles a call and
\ *    it is what lets sn_write leave X and Y alone.
\ *
\ * 2. THE CHIP'S REGISTERS ARE CACHED (sn_cache_*). A tone or volume
\ *    byte is only sent when the register does not already hold it,
\ *    which is 44-81% of them - see docs/performance.md. Anything that
\ *    writes the SN behind this layer's back must call sn_forget, or
\ *    the cache goes on claiming it knows what is in the chip.
\ ******************************************************************

\ A complete sweep of the AY's 5-bit envelope ladder averages 0.1961 of
\ full amplitude, which is level 12. ym_sn_vol maps that to SN attenuation
\ 9 since the volume curve became ym2sn's (it was 7 under the dB-faithful
\ one). The 0.1961 is a fact about the AY and does not move with the
\ curve; whether the LEVEL is still the right thing to emit once the
\ mapping has changed is an E2/E3 question, and the measurement says it is
\ near enough - EDGEA's volumes went from 28.7% of ym2sn's to 97.4% with
\ this constant untouched, and a third of that tune is envelope.
ENV_MEAN_LEVEL  = 12

\ The envelope completes a whole cycle within one 50 Hz call when its
\ period is 78 or less: 5120000 / 78 > 65536, one full turn of the phase.
ENV_FULL_PERIOD = 78

.ay2sn
{
    lda #255 : sta &fe43        \ DDRA once a call, not once a byte

    \ ---- the envelope generator, once for all three channels -------
    \ ONE test, not two. Whether the envelope completes whole cycles inside
    \ a call decides BOTH the step and which level goes out, and it used to
    \ be worked out twice - once here and once again forty cycles later,
    \ re-reading the same two registers to reach the same answer.
    lda ay_regs+12
    bne slow_env                \ period >= 256: a step under 20000, rare
    ldy ay_regs+11
    lda env_recip_lo,y : sta env_step
    lda env_recip_hi,y : sta env_step+1
    cpy #ENV_FULL_PERIOD + 1
    bcc fast_env
    bcs got_step                \ always
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
    jmp env_done

.fast_env
    \ A single sample is only the right answer for a SLOW envelope. Every
    \ envelope in EDGEA runs 1.17 to 2.89 complete cycles per call, so what
    \ the ear gets is the MEAN of the ramp while we emit whichever point we
    \ happened to land on. The PHASE still advances - a later slow envelope
    \ resumes from it - but the sample is never taken, so the shift, the
    \ table lookup and the second test all go. See docs/fidelity-plan.md.
    clc
    lda env_phase   : adc env_step   : sta env_phase
    lda env_phase+1 : adc env_step+1 : sta env_phase+1
    lda #ENV_MEAN_LEVEL
    sta env_level

.env_done

    lda #15                     \ nothing has the noise open yet
    sta noise_att
    lda #255                    \ and no channel has claimed the bass
    sta bass_chan
    sta bass_skip
    lda #0 : sta sn_slot+0      \ every channel on its own SN tone slot,
    lda #1 : sta sn_slot+1      \ until the periodic bass moves one
    lda #2 : sta sn_slot+2
    jsr bass_pick               \ decide now which channel may take the voice

    ldx #0
.ch_loop
    \ ---- volume ----------------------------------------------------
    lda ay_regs+8,x
    and #16
    beq fixed_vol
    lda env_level
    jmp have_vol5
.fixed_vol
    \ 4-bit volume -> the 5-bit scale the envelope also uses, so that one
    \ table serves both. ym2sn widens it by DUPLICATING the low bit,
    \ (v << 1) | (v & 1), and the difference from the (v << 1) | 1 that was
    \ here is one attenuation step on every EVEN volume - half the levels
    \ in the tune. Measured, it is half of what stood between this
    \ converter and ym2sn's own output: see tools/make_tables.py's
    \ ym_sn_vol. A table because the 6502 has no cheap way to say it.
    lda ay_regs+8,x
    and #15
    tay
    lda ay_vol5,y
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
    cpx bass_want
    bne fit                     \ not the channel the voice was given to
    jsr bass_claim
.fit
    lda snper+1
    cmp #4
    bcc fits
.halve
    lsr snper+1
    ror snper
    lda snper+1
    cmp #4
    bcs halve
.fits
    lda snper
    ora snper+1
    bne nonzero
    inc snper                   \ never write a period of zero
.nonzero

    \ ---- park this channel's SN bytes; the writes come after the loop
    \ Through sn_slot, because the periodic bass has to be emitted on SN
    \ tone slot 2 - rate 3 clocks the noise from tone generator 3 and
    \ nothing else will do - and it swaps two channels round to get there.
    ldy sn_slot,x
    lda snper
    and #15
    ora sn_tone_latch,y
    sta sn_t0,x
    lda att                     \ the volume byte NOW, while Y is still the
    ora sn_vol_latch,y          \ slot: the nibble tables below want Y
    sta sn_v,x
    ldy snper+1                 \ snper+1 << 4, from a four-entry table
    lda sn_hi4,y
    sta tmp2
    lda snper
    lsr a : lsr a : lsr a : lsr a
    ora tmp2
    sta sn_t1,x

    inx
    cpx #3
    beq chans_done
    jmp ch_loop
.chans_done
    \ ---- the nine tone/volume writes, X now free for sn_write -----
    \ A SOFTWARE bass channel's volume is the interrupt's to write - it is
    \ the square wave - so this must not stamp on it once a call. That is
    \ bass_skip, and it is 255 for the periodic bass, whose tone slot has
    \ to be written silent here like any other.
    ldx #0 : jsr sn_chan
    ldx #1 : jsr sn_chan
    ldx #2 : jsr sn_chan

    \ ---- the periodic bass owns the noise channel when it is playing
    \ The note sounds on the noise generator, clocked by tone generator 3
    \ at a fifteenth of its frequency, at the claiming channel's own
    \ volume. bass_pick only grants the voice when no drum wants the
    \ channel, so there is nothing to arbitrate here.
    lda bass_mode
    cmp #2
    bne drums
    lda bass_chan
    bmi drums
    lda #&e3                    \ bit 2 CLEAR = periodic; rate 3 = tone 3
    cmp noise_last              \ but only if it has changed: writing the
    beq per_same                \ noise register RESETS the LFSR, which is
    sta noise_last              \ a click on every retune. ym2sn dedupes it
    jsr sn_write                \ for the same reason.
.per_same
    lda bass_att
    ora #&f0
    jsr sn_vol3
    jmp bass_update
.drums

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
    jsr sn_vol3
    jmp bass_update
.no_noise
    lda #&ff                    \ channel 3 silent
    jsr sn_vol3
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
\ * untouched. It costs a timer and two interrupts per cycle: 102 to
\ * 157 a second on the tunes measured, about 0.5% of the CPU.
\ *
\ * bass_mode 2 is the other answer: the PERIODIC-NOISE bass, which needs
\ * no timer and no interrupts at all but plays on the noise channel, so
\ * the drums take it away whenever they want it - the median song in the
\ * corpus, 10% of its bass calls. See bass_claim's .periodic.
\ *
\ * ONE voice. That is enough for every frame of Rhino's Acid Demo, 83%
\ * of Dead On Time and 91% of EDGEA; the rest octave-shift as before.
\ *
\ * TO USE THE SOFTWARE VOICE the host must:
\ *   1. put User VIA T1 in FREE-RUN mode (ACR bit 6 set, bit 7 clear),
\ *      so it reloads itself and the interrupt only has to toggle;
\ *   2. call bass_irq when User VIA T1 interrupts - and test the flag
\ *      AGAINST THE ENABLE, `lda IFR : and IER : and #&40`. Masking a
\ *      VIA interrupt does not stop its timer, so bit 6 goes on being
\ *      set while T1 is disabled, and testing IFR alone will service
\ *      the bass on the back of every other interrupt in the machine;
\ *   3. set bass_mode to 1.
\ * TO USE THE PERIODIC ONE, set bass_mode to 2. That is all: no timer,
\ * no interrupt, nothing to wire up. Leave bass_mode at 0 and neither
\ * runs - the octave shift stays.
\ *
\ * The bass is only as steady as the interrupt latency, so a host that
\ * disables interrupts for long stretches will hear the pitch wobble.
\ ******************************************************************

USR_T1CL = &FE64        \ counter, low  - reading it clears the interrupt
USR_T1CH = &FE65        \ counter, high - writing it starts the timer
USR_T1LL = &FE66        \ latch, low    - the period of the NEXT cycle...
USR_T1LH = &FE67        \ latch, high   - ...without restarting this one
USR_IFR  = &FE6D
USR_IER  = &FE6E

\ ******************************************************************
\ * bass_pick - which channel gets the voice this call, into bass_want.
\ *
\ * There is one voice and a tune can want two, so something has to
\ * choose - and choosing "the first one below the floor" makes the
\ * voice THRASH. Measured on Targhan's Dead On Time: the lowest-numbered
\ * channel below the floor changes on 17.7% of bass calls, with a median
\ * run of ONE call, so the bass would hop between channels 25 times a
\ * second and be retuned every time. (Rhino's tune never changes channel
\ * and EDGEA changes on 2.4%.)
\ *
\ * So it is sticky: if the channel that had the voice last call still
\ * wants it, it keeps it. Only when that channel comes back above the
\ * floor does the voice move, and then to the lowest-numbered claimant.
\ ******************************************************************
.bass_pick
{
    lda #255
    sta bass_want
    lda bass_mode
    beq out                     \ mode 0: nobody gets it

    \ Which channels are audible and below the chip's floor?
    lda #0
    sta bass_mask
    sta noise_busy
    ldx #2
.scan
    lda ay_regs+8,x
    and #31
    beq next                    \ silent: no drum and no bass either
    lda ay_regs+7
    and noise_bit,x
    bne no_drum
    inc noise_busy              \ the noise is open here AND has a volume
.no_drum
    lda ay_regs+7
    and tone_bit,x
    bne next                    \ tone disabled
    ldy per_idx,x
    lda ay_regs+1,y
    and #15
    cmp #2                      \ AY period >= 512 is below 122 Hz
    bcc next
    lda chan_bit,x
    ora bass_mask
    sta bass_mask
.next
    dex
    bpl scan

    lda bass_mask
    beq out                     \ nobody wants it

    lda bass_mode               \ the periodic voice IS the noise channel,
    cmp #2                      \ so a drum takes it away - ym2sn's rule,
    bne claimable               \ and measured it costs the median song 10%
    lda noise_busy              \ of its bass calls (survey_tunes.py). The
    bne out                     \ software voice has no such problem.
.claimable

    ldx bass_prev               \ does last call's channel still want it?
    bmi lowest
    lda chan_bit,x
    and bass_mask
    bne take
.lowest
    ldx #0                      \ no: the lowest-numbered claimant
    lda bass_mask
    lsr a : bcs take
    inx
    lsr a : bcs take
    inx
.take
    stx bass_want
.out
    rts
}

.chan_bit       equb 1, 2, 4

\ snper+1 << 4, for packing a ten-bit period into the SN's second tone
\ byte: four shifts become a lookup, and snper+1 is 0-3 by the time the
\ halving loop is done, so four entries is the whole domain.
\ The matching table for the other half - snper >> 4, 256 entries - was
\ built and thrown away. It saved 4 more cycles a channel and cost 256
\ bytes plus up to 255 of ALIGN padding, and small is what this library
\ is for: 12 cycles a call is not worth half a page.
.sn_hi4         equb 0, 16, 32, 48

\ ******************************************************************
\ * bass_claim - X = channel, snper = 2 * the AY period. Called from the
\ * channel loop when the note is below the chip's floor.
\ ******************************************************************
.bass_claim
{
    stx bass_chan
    lda bass_mode
    cmp #2
    beq periodic

    stx bass_skip               \ the interrupt owns this channel's volume

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

\ ---- the periodic-noise voice ---------------------------------------
\ The SN's noise generator, with the feedback bit clear, circulates a
\ single set bit round its 15-bit shift register: a 1/15 duty-cycle pulse
\ train at a fifteenth of whatever clocks it. Rate 3 clocks it from tone
\ generator 3, so tone 3's period sets the pitch and the whole bass
\ register is in reach - 8 Hz to 7.8 kHz against the tone channels' 122 Hz
\ floor. This is what ym2sn.py does, and the timbre is its timbre: thin
\ and reedy, not a square wave.
.periodic
    \ snper is 2 * the AY period, and the SN wants a fifteenth of it.
    \ ROUNDED, which is ym2sn's own int(round()) - see div15.
    jsr div15

    \ The note is played by the noise channel at this channel's volume,
    \ and the tone slot that clocks it must be silent. bass_skip stays
    \ 255: unlike the software voice, that silence is ours to write.
    lda att : sta bass_att
    lda #15 : sta att

    \ ...and this channel has to BE tone slot 2. Swap it with whoever is
    \ there; the other two channels keep sounding on the slots that are
    \ left, so the periodic bass costs no musical channel - only the drums.
    ldy sn_slot,x
    lda sn_slot+2 : sta sn_slot,x
    tya           : sta sn_slot+2
    rts
}

\ ******************************************************************
\ * div15 - snper = round(snper / 15). Exact, and exactly ym2sn's value.
\ *
\ * No loop and no table. 256 = 15*17 + 1, so for x = 256h + l
\ *
\ *     x = 15*17h + (h + l)   and therefore   x/15 = 17h + (h + l)/15
\ *
\ * with h + l at most 287, which the same identity reduces to a single
\ * byte; and for a byte v = 16a + b the remainder feeds back just once,
\ * because a + b is at most 30. So the whole division is two adds, a
\ * nibble swap and two compares.
\ *
\ * Adding 7 first turns the floor into a round, which is what ym2sn's
\ * int(round(sn_tone)) does - proved equal on every value in the range
\ * (snper is 1024 to 8190, a period of 68 to 546). Rounding rather than
\ * truncating matters: at the bottom of the range one step of the period
\ * is 25 cents, and rounding halves the worst error to 11.8 - which is
\ * the chip's own quantisation and no more.
\ ******************************************************************
.div15
{
    clc
    lda snper   : adc #7 : sta d_m       \ d_m = l, A+carry -> h
    lda snper+1 : adc #0 : sta d_q+1     \ d_q+1 = h, 0..32

    clc
    adc d_m                              \ t = h + l, 0..287
    bcc byte                             \ ...and if it carried, t = 256 + A,
    adc #0                               \ so t/15 = 17 + (1 + A)/15. The ADC
    sta d_m                              \ adds the 1 with the carry still set
    lda #17
    bne have17                           \ always
.byte
    sta d_m
    lda #0
.have17
    sta d_q                              \ the 17, or nothing

    lda d_m                              \ v/15 for a byte: v = 16a + b, and
    lsr a : lsr a : lsr a : lsr a        \ a + b never needs a second pass
    sta snper                            \ a
    lda d_m : and #15
    clc : adc snper                      \ u = a + b, 0..30
    cmp #15
    bcc no_one
    inc snper
    cmp #30
    bcc no_one
    inc snper                            \ only v = 255 reaches here
.no_one
    lda snper : clc : adc d_q : sta d_q  \ + the 17 from the carry above

    \ and 17h on top: (h << 4) + h, sixteen bits
    lda d_q+1 : sta snper
    lda #0    : sta snper+1
    asl snper : rol snper+1
    asl snper : rol snper+1
    asl snper : rol snper+1
    asl snper : rol snper+1
    clc
    lda snper   : adc d_q+1 : sta snper
    lda snper+1 : adc #0    : sta snper+1
    clc
    lda snper   : adc d_q : sta snper
    lda snper+1 : adc #0  : sta snper+1
    rts
}

\ ******************************************************************
\ * bass_update - start, retune or stop the timer. Ends the frame.
\ ******************************************************************
.bass_update
{
    lda bass_chan
    sta bass_prev               \ so bass_pick can keep it next call
    bpl playing
    jmp bass_stop               \ nothing wants it: shut the timer down

.playing
    lda bass_mode               \ the periodic voice has no timer at all;
    cmp #2                      \ but if the host has just switched to it
    bne software                \ from the software voice, stop that one
    lda bass_running
    beq no_timer
    jmp bass_timer_off
.no_timer
    rts

.software
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
\ * bass_stop - silence the bass voice and shut its timer down.
\ *
\ * It deliberately does NOT write the channel's volume. bass_update runs
\ * at the END of a call, after the volume writes, and on a call where
\ * nobody claimed the voice the channel's own volume has already gone
\ * out correctly. An earlier version wrote it here as well - and got it
\ * wrong, forcing volume 0, full blast, for one call every time the bass
\ * stopped. That was an audible click on every bass note ending.
\ ******************************************************************
.bass_stop
{
    \ UNCONDITIONAL. An earlier version only touched the hardware when
    \ bass_running said the timer was going, and the flag and the chip
    \ got out of step - mute left the timer running and the interrupt
    \ wrote the channel back up fifty times a second underneath it.
    \ Silencing a timer that is already silent costs 16 cycles.
    lda #&FF : sta bass_last        \ force a retune when it comes back
    sta bass_prev
    \ falls into bass_timer_off
}

\ ******************************************************************
\ * bass_timer_off - the hardware half of bass_stop, on its own so that
\ * a host switching from the software voice to the periodic one has one
\ * place to turn the timer off rather than a second copy of this.
\ ******************************************************************
.bass_timer_off
{
    lda #0   : sta bass_running
    lda #&40 : sta USR_IER          \ bit 7 clear = disable T1
    sta USR_IFR                     \ and drop an interrupt already pending,
    rts                             \ or it writes one more stale volume
}

\ ******************************************************************
\ * bass_irq - call this when User VIA T1 interrupts. Half a cycle of
\ * the bass square wave. Uses A only.
\ ******************************************************************
.bass_irq
{
    \ Clear the timer's interrupt flag by writing the bit back to IFR,
    \ which is the documented way and needs no reasoning about the side
    \ effects of reading a counter. (Reading T1C-L also clears it and
    \ worked; this is simply the unambiguous form.)
    lda #&40
    sta USR_IFR
    lda #255 : sta &fe43
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
    rts
}

\ ******************************************************************
\ * sn_chan - X = channel. Its three SN bytes, but only the ones the
\ * chip does not already hold.
\ *
\ * The SN's tone and volume registers LATCH, so re-sending a byte a
\ * register already has is audibly nothing and costs 38 cycles - and
\ * measured over the corpus, 44-81% of what this layer used to send was
\ * exactly that. Ten bytes of cache buy it back.
\ *
\ * The cache is indexed by SN SLOT, not by channel: the periodic bass
\ * swaps a channel onto tone slot 2, and it is the slot that names the
\ * register. A tone is a latch/data PAIR and is compared as one - the
\ * low nibble alone changing is still a different note.
\ ******************************************************************
.sn_chan
{
    ldy sn_slot,x
    lda sn_t0,x
    cmp sn_cache_t0,y
    bne do_tone
    lda sn_t1,x
    cmp sn_cache_t1,y
    beq tone_same
.do_tone
    lda sn_t0,x : sta sn_cache_t0,y : jsr sn_write
    lda sn_t1,x : sta sn_cache_t1,y : jsr sn_write
.tone_same
    cpx bass_skip
    beq irq_owns
    lda sn_v,x
    cmp sn_cache_v,y
    beq out
    sta sn_cache_v,y
    jmp sn_write
.irq_owns
    \ The software bass interrupt writes this channel's volume behind the
    \ cache's back, so whatever the cache holds is a lie. &00 is not a
    \ volume byte any path can emit - they are &9x, &bx and &dx - so it
    \ forces the write on the first call after the bass gives the channel
    \ back. Without it the channel stays stuck at the square wave's level.
    lda #0
    sta sn_cache_v,y
.out
    rts
}
.sn_cache_t0 skip 3
.sn_cache_t1 skip 3
.sn_cache_v  skip 4     \ three tone channels, then the noise channel

\ Invalidate the cache: the next call rewrites everything. Anything that
\ writes the SN behind this layer's back - akl_silence's four volume-off
\ bytes, a host's own sound code - has to call this or the cache goes on
\ claiming it knows what is in the chip. &00 is not a byte any cached
\ register can legally hold, which is what makes it the invalid marker.
.sn_forget
{
    lda #0
    ldx #9
.wipe
    sta sn_cache_t0,x
    dex
    bpl wipe
    rts
}

\ The noise CHANNEL's volume - SN register 7 - latches like every other,
\ and it was the one byte still going out on every single call: the drum
\ path, the silent path and the periodic bass all wrote it
\ unconditionally. Caught by capturing the REAL write stream out of
\ jsbeeb; the simulator had been told to expect it and did not blink.
.sn_vol3
{
    cmp sn_cache_v+3
    beq same
    sta sn_cache_v+3
    jmp sn_write
.same
    rts
}

\ One byte to the SN76489, through the System VIA and the addressable
\ latch. Started as lib/vgiplayer.asm's, less the `ldx #255 : stx &fe43`
\ that set DDRA on every byte: that is the caller's now, once a call
\ rather than ten times (see the header), which is why this uses no
\ index register at all and leaves X and Y for its callers.
.sn_write
{
    sta &fe4f
    lda #0
    sta &fe40
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

.bass_mode    skip 1        \ 0 = octave-shift, 1 = software, 2 = periodic
.bass_chan    skip 1        \ 0-2 while a voice is claimed, 255 otherwise
.bass_skip    skip 1        \ the channel whose volume ay2sn must NOT write
.bass_att     skip 1        \ the periodic voice's volume, for the noise chan
.noise_busy   skip 1        \ is a drum using the noise channel this call?
.sn_slot      skip 3        \ channel -> SN tone slot; identity but for B1
.d_q          skip 2        \ div15's quotient...
.d_m          skip 1        \ ...and the remainder it feeds back
.bass_running skip 1        \ is the timer going?
.bass_phase   skip 1        \ which half of the square wave is next
.bass_on      skip 1        \ the channel's volume byte, sounding...
.bass_off     skip 1        \ ...and silent
.bass_n       skip 2        \ the timer count: half a period, in us
.bass_last    skip 2        \ what the timer was last actually given
.bass_want    skip 1        \ the channel bass_pick chose this call
.bass_prev    skip 1        \ ...and the one it chose last call
.bass_mask    skip 1        \ which channels are below the floor

\ 4-bit AY volume -> the 5-bit scale, (v << 1) | (v & 1): ym2sn's widening,
\ which fills 0-31 rather than leaving the top of the range unreachable.
.ay_vol5        equb 0, 3, 4, 7, 8, 11, 12, 15, 16, 19, 20, 23, 24, 27, 28, 31
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
    lda #255 : sta &fe43
    jsr sn_forget               \ these four writes go round the cache
    jsr bass_stop               \ mute has to stop the bass too, or its
    lda #&9f : jsr sn_write     \ interrupt writes the channel straight
                                \ back up again fifty times a second
    lda #&bf : jsr sn_write
    lda #&df : jsr sn_write
    lda #&ff : jmp sn_write
}
