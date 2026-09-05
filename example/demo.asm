\ ******************************************************************
\ * demo.asm - the smallest thing that plays an Arkos song on a BBC.
\ *
\ * One player, one song, a 50 Hz interrupt, and a raster bar so the
\ * cost is visible. Assembled once per player by example/build.py,
\ * which also exports the song and writes example/build/config.asm.
\ *
\ * The whole integration is four things, and they are all any host
\ * has to do:
\ *
\ *   1. INCLUDE the player's .h.asm inside your zero page.
\ *   2. INCLUDE lib/ay2sn.asm and the player.
\ *   3. Call <player>_init once, with the address of the song.
\ *   4. Call <player>_play then ay2sn once per 50 Hz field.
\ *
\ * The MOS is not involved in the sound at all: ay2sn drives the
\ * SN76489 through the System VIA itself.
\ ******************************************************************

CPU 0

OSWRCH   = &FFEE
OSBYTE   = &FFF4
IRQ1V    = &0204
\ VDU 13 is a CARRIAGE RETURN and nothing more. Without a line feed
\ beside it, every line of the banner overwrites the one before.

SYS_IFR  = &FE4D                \ System VIA: VSync is bit 1
USR_T1CL = &FE64                \ User VIA timer 1 - the raster timer.
USR_T1CH = &FE65                \ Free on a BBC (the System VIA's T1 is
USR_ACR  = &FE6B                \ the MOS's 100 Hz tick, and taking it
USR_IFR  = &FE6D                \ would break the OS)
USR_IER  = &FE6E

\ VSync happens in the vertical blanking, and the music is over long
\ before the first scanline is drawn - so a band painted around it is
\ invisible. Fire the music this many microseconds after VSync instead,
\ 100 scanlines at 64us, which is below the banner.
RASTER_DELAY = 100 * 64

LOAD     = &1900            \ DFS PAGE
SONG     = &3000            \ where the tracker data is assembled

\ PLAYER_AKY and SONG_TITLE come from the generated config.
INCLUDE "example/build/config.asm"

\ ---- zero page -----------------------------------------------------
ORG &70
IF PLAYER_AKY
INCLUDE "lib/akyplayer.h.asm"
ELSE
INCLUDE "lib/aklplayer.h.asm"
ENDIF
.muted          skip 1
.mute_latch     skip 1
.old_irq        skip 2
GUARD &9F

\ ---- code ----------------------------------------------------------
ORG LOAD
GUARD SONG
.start

.main
{
    lda #22 : jsr OSWRCH            \ MODE 4: 40 columns, and its screen
    lda #4  : jsr OSWRCH            \ starts at &5800, well clear of the
                                    \ song at &3000. MODE 1's starts AT
                                    \ &3000 and quietly erased it.

    ldx #0
.print
    lda banner,x
    beq printed
    jsr OSWRCH
    inx
    bne print
.printed

    lda #0
    sta muted
    sta mute_latch

IF PLAYER_AKY
    \ The base of the exported data: aky_init reads the AKY header
    \ itself and finds the linker past it.
    lda #LO(SONG) : ldx #HI(SONG)
    jsr aky_init
ELSE
    lda #LO(SONG) : ldx #HI(SONG) : ldy #0
    jsr akl_init
ENDIF

    jsr install_irq

.loop
    lda #&81                        \ SPACE down? (internal key 98)
    ldx #(256 - 98) : ldy #&FF
    jsr OSBYTE
    cpx #&FF
    bne space_up
    lda mute_latch
    bne check_esc
    lda muted : eor #1 : sta muted
    lda #1 : sta mute_latch
    jmp check_esc
.space_up
    lda #0 : sta mute_latch

.check_esc
    lda #&81                        \ ESCAPE down? (internal key 112)
    ldx #(256 - 112) : ldy #&FF
    jsr OSBYTE
    cpx #&FF
    bne loop

    jsr remove_irq
    jsr silence
    lda #22 : jsr OSWRCH
    lda #7  : jsr OSWRCH
    rts
}

\ ******************************************************************
\ * the 50 Hz interrupt
\ ******************************************************************
.install_irq
{
    sei
    lda IRQ1V   : sta old_irq
    lda IRQ1V+1 : sta old_irq+1
    lda #LO(irq_handler) : sta IRQ1V
    lda #HI(irq_handler) : sta IRQ1V+1

    lda USR_ACR : sta old_acr    \ User VIA timer 1, one-shot mode
    and #&3F    : sta USR_ACR
    lda #&C0    : sta USR_IER    \ enable its interrupt
    cli
    rts
}
.old_acr skip 1

.remove_irq
{
    sei
    lda #&40      : sta USR_IER  \ disable it again, and put the
    lda old_acr   : sta USR_ACR  \ User VIA back as the MOS had it
    lda old_irq   : sta IRQ1V
    lda old_irq+1 : sta IRQ1V+1
    cli
    rts
}

\ The MOS has already saved A in &FC by the time IRQ1V is called, so A
\ is ours to use; X and Y are not.
\ Two interrupts, and the second one is only for the demonstration:
\ VSync starts a one-shot timer, and the music runs when THAT fires, a
\ few scanlines into the visible display. A real host would simply call
\ music_frame at VSync - but the music is over well before the first
\ scanline is drawn, so a band painted around it there is invisible,
\ which is exactly what the first version of this demo did.
.irq_handler
{
    lda USR_IFR
    and #&40                        \ User VIA timer 1: the raster point
    bne do_music

    lda SYS_IFR
    and #2                          \ System VIA: VSync
    beq chain
    sta SYS_IFR                     \ clear it
    lda #LO(RASTER_DELAY) : sta USR_T1CL
    lda #HI(RASTER_DELAY) : sta USR_T1CH    \ writing the high byte starts it
    jmp chain

.do_music
    lda USR_T1CL                    \ reading it clears the timer's flag
    txa : pha
    tya : pha
    lda #6 : jsr band               \ red: the band starts here
    jsr music_frame
    lda #7 : jsr band               \ black: and it ends here
    pla : tay
    pla : tax
.chain
    jmp (old_irq)
}

\ ******************************************************************
\ * one frame of music - the whole of the library's API, in use
\ ******************************************************************
.music_frame
{
    lda muted
    bne do_silence      \ Mute is INSTEAD OF a frame of music, never as
IF PLAYER_AKY           \ well as. Running the player and silencing the
    jsr aky_play        \ chip after it puts a burst of the tune's own
ELSE                    \ volumes out fifty times a second, and crackles.
    jsr akl_play
ENDIF
    jmp ay2sn
.do_silence
    jmp silence
}

\ Paint logical colour 0 a physical colour. A is (physical EOR 7).
\ ONE write to &FE21 sets ONE of the SIXTEEN palette entries, and a
\ 1 bpp mode spreads each logical colour over EIGHT of them: 0-7 are
\ logical 0 and 8-15 are logical 1 (measured in jsbeeb, 2026-09-05 -
\ writing entry 0 alone bands part of every character cell, and the
\ even entries are not the set either). So eight writes, and the text
\ in logical 1 is left alone. A 4-colour mode needs four writes per
\ colour and a 16-colour mode one.
.band
{
    sta band_col
    ldx #7
.next
    txa
    asl a : asl a : asl a : asl a
    ora band_col
    sta &FE21
    dex
    bpl next
    rts
}
.band_col skip 1

\ silence: the four volume-off writes. It lives in ay2sn.asm and is not
\ AKL-specific, despite the name it arrived with.
.silence
    jmp akl_silence

.banner
IF PLAYER_AKY
    EQUS 13, 10, 13, 10, "  Arkos Tracker AKY replay for the BBC Micro", 13, 10
ELSE
    EQUS 13, 10, 13, 10, "  Arkos Tracker AKL replay for the BBC Micro", 13, 10
ENDIF
    EQUS 13, 10, "  ", SONG_TITLE, 13, 10
    EQUS 13, 10, "  The red band is the music.", 13, 10
    EQUS "  SPACE mutes.  ESCAPE quits.", 13, 10
    EQUB 0

\ ---- the library ---------------------------------------------------
INCLUDE "lib/ay2sn.asm"
IF PLAYER_AKY
INCLUDE "lib/akyplayer.asm"
ELSE
INCLUDE "lib/aklplayer.asm"
ENDIF

.code_end

\ ---- the song ------------------------------------------------------
CLEAR SONG, SONG + 1
ORG SONG
GUARD &5800                     \ MODE 4's screen starts here
.song_data
INCBIN "example/build/song.bin"
.song_end

PRINT "code", ~start, "-", ~code_end, " song", ~song_data, "-", ~song_end
PRINT "spare between code and song =", ~SONG - code_end

IF PLAYER_AKY
SAVE "AKYDEMO", start, song_end, main
ELSE
SAVE "AKLDEMO", start, song_end, main
ENDIF
