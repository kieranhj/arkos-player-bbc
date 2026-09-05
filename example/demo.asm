\ ******************************************************************
\ * demo.asm - the smallest thing that plays an Arkos song on a BBC.
\ *
\ * One player, one song, a 50 Hz interrupt, and a raster bar so the
\ * cost is visible. Assembled once per player by example/build.ps1,
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
VIA_IFR  = &FE4D

LOAD     = &1900            \ DFS PAGE
SONG     = &3000            \ where the tracker data is assembled

\ PLAYER_AKY and AKY_LINKER come from the generated config.
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
    \ Past the AKY header: one flags byte, one channel count, then a
    \ four-byte PSG frequency per PSG. build.ps1 measured it.
    lda #LO(SONG + AKY_LINKER)
    ldx #HI(SONG + AKY_LINKER)
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
    cli
    rts
}

.remove_irq
{
    sei
    lda old_irq   : sta IRQ1V
    lda old_irq+1 : sta IRQ1V+1
    cli
    rts
}

\ The MOS has already saved A in &FC by the time IRQ1V is called, so A
\ is ours to use; X and Y are not.
.irq_handler
{
    lda VIA_IFR
    and #2                          \ System VIA, VSync
    beq chain
    sta VIA_IFR                     \ clear it
    txa : pha
    tya : pha
    lda #6 : sta &FE21              \ logical 0 -> red: the band starts
    jsr music_frame
    lda #7 : sta &FE21              \ logical 0 -> black: and it ends
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

\ silence: the four volume-off writes. It lives in ay2sn.asm and is not
\ AKL-specific, despite the name it arrived with.
.silence
    jmp akl_silence

.banner
IF PLAYER_AKY
    EQUS 13, 13, "  Arkos Tracker AKY replay for the BBC Micro", 13
ELSE
    EQUS 13, 13, "  Arkos Tracker AKL replay for the BBC Micro", 13
ENDIF
    EQUS 13, "  ", SONG_TITLE, 13
    EQUS 13, "  The red band is the music.", 13
    EQUS "  SPACE mutes.  ESCAPE quits.", 13
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
