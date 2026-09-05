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

\ NEGATIVE INKEY numbers, measured in jsbeeb 2026-09-05 by holding the
\ key and scanning INKEY(-1) to INKEY(-128). They are NOT the internal
\ key numbers an OSBYTE 121 scan or a VIA matrix read uses - they are
\ one MORE. SPACE is internal 98 and negative INKEY 99; ESCAPE is
\ internal 112 and negative INKEY 113. Using the internal number here
\ reads the neighbouring key and the key appears dead.
KEY_SPACE  = 99
KEY_ESCAPE = 113
KEY_B      = 101
IRQ1V    = &0204
\ VDU 13 is a CARRIAGE RETURN and nothing more. Without a line feed
\ beside it, every line of the banner overwrites the one before.

SYS_IFR  = &FE4D                \ System VIA: VSync is bit 1

\ Both User VIA timers are in use, and which job goes to which is not
\ arbitrary. T2 is a ONE-SHOT ONLY timer, which is exactly what firing
\ once at a scanline wants. T1 has a FREE-RUN mode that reloads itself,
\ which is exactly what a square wave wants - so the bass gets T1 and
\ its interrupt only has to toggle a volume.
\ (The System VIA's T1 is the MOS's 100 Hz tick; taking it breaks the OS.)
USR_T2CL = &FE68                \ raster: one-shot, fired from VSync
USR_T2CH = &FE69
USR_ACR  = &FE6B
IFR_T1   = &40                  \ the bass
IFR_T2   = &20                  \ the raster point
\ USR_IFR and USR_IER are lib/ay2sn.asm's - it drives T1 itself.

\ VSync happens in the vertical blanking, and the music is over long
\ before the first scanline is drawn - so a band painted around it is
\ invisible. Fire the music this many microseconds after VSync instead,
\ 145 scanlines at 64us, which is below the banner (MODE 6 rows are
\ ten scanlines tall, so the text reaches about 120).
RASTER_DELAY = 145 * 64

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
.field_count    skip 1      ; fields until the next call to the player
.old_irq        skip 2
GUARD &9F

\ ---- code ----------------------------------------------------------
ORG LOAD
GUARD SONG
.start

.main
{
    lda #22 : jsr OSWRCH            \ MODE 6: 40 columns, and its screen
    lda #6  : jsr OSWRCH            \ starts at &6000, leaving 12K for the
                                    \ song at &3000 - a six-channel AKY
                                    \ export needs more than MODE 4's 10K.
                                    \ (MODE 1's screen starts AT &3000 and
                                    \ quietly erased the song.) Still a
                                    \ 1 bpp mode, so the band is the same.

    ldx #0                          \ VDU 23,1,0,0,0,0,0,0,0,0 - cursor off.
.curs                               \ Its own loop because the banner's is
    lda cursor_off,x                \ zero-terminated and this is mostly
    jsr OSWRCH                      \ zeroes.
    inx
    cpx #10
    bne curs

    ldx #0
.print
    lda banner,x
    beq printed
    jsr OSWRCH
    inx
    bne print
.printed

    lda #229 : ldx #1 : ldy #0      \ *FX229,1 - ESCAPE becomes an ordinary
    jsr OSBYTE                      \ key instead of an escape condition,
                                    \ which is the only way to poll it

    lda #0
    sta muted
    sta mute_latch
    lda #REPLAY_DIV
    sta field_count
    lda #2                          \ hand the low notes to the periodic
    sta bass_mode                   \ noise instead of shifting them up
    jsr show_bass                   \ - the default because it needs no
                                    \ timer and no interrupt, so it is what
                                    \ most hosts can actually afford. B
                                    \ cycles to the software voice and off.

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
    lda #&81                        \ B down? cycle the bass through OFF,
    ldx #(256 - KEY_B) : ldy #&FF   \ the software voice and the periodic
    jsr OSBYTE                      \ one, so all three can be compared
    cpx #&FF
    bne b_up
    lda b_latch
    bne after_b
    lda bass_mode : clc : adc #1
    cmp #3 : bcc b_ok
    lda #0
.b_ok
    sta bass_mode
    lda #1 : sta b_latch
    jsr show_bass
    jmp after_b
.b_up
    lda #0 : sta b_latch
.after_b

    lda #&81                        \ SPACE down?
    ldx #(256 - KEY_SPACE) : ldy #&FF
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
    lda #&81                        \ ESCAPE down?
    ldx #(256 - KEY_ESCAPE) : ldy #&FF
    jsr OSBYTE
    cpx #&FF
    bne loop

    jsr remove_irq
    jsr silence
.wait_release                       \ hand ESCAPE back only once it is up,
    lda #&81                        \ or the MOS raises the escape condition
    ldx #(256 - KEY_ESCAPE) : ldy #&FF
    jsr OSBYTE
    cpx #&FF
    beq wait_release
    lda #229 : ldx #0 : ldy #0      \ give ESCAPE back to the MOS
    jsr OSBYTE
    lda #22 : jsr OSWRCH
    lda #7  : jsr OSWRCH
    rts
}

\ ******************************************************************
\ * the 50 Hz interrupt
\ ******************************************************************
\ Print which bass the library is using, at the end of the "Bass:" line.
\ Five characters, always: OFF, SOFT (a VIA timer bit-banging a square
\ wave) or NOISE (the SN's periodic noise, no interrupts).
.show_bass
{
    ldx #0
.pos
    lda bass_at,x : jsr OSWRCH
    inx : cpx #3 : bne pos
    lda bass_mode
    asl a : asl a               \ five bytes a name: 4 * mode + mode
    clc : adc bass_mode
    tay
    ldx #5
.name
    lda bass_names,y : jsr OSWRCH
    iny : dex : bne name
    rts
}
.b_latch skip 1

.install_irq
{
    sei
    lda IRQ1V   : sta old_irq
    lda IRQ1V+1 : sta old_irq+1
    lda #LO(irq_handler) : sta IRQ1V
    lda #HI(irq_handler) : sta IRQ1V+1

    lda USR_ACR : sta old_acr    \ T1 free-run (bit 6), T2 interval (bit 5
    and #&1F                     \ clear), and no PB7 output (bit 7 clear)
    ora #&40    : sta USR_ACR
    lda #&E0    : sta USR_IER    \ enable both timers' interrupts
    cli
    rts
}
.old_acr     skip 1
.via_pending skip 1

.remove_irq
{
    sei
    lda #&60      : sta USR_IER  \ disable both again, and put the
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
    \ AND THE FLAGS WITH THE ENABLES. Masking a VIA interrupt does not
    \ stop its timer: T1 keeps free-running and keeps SETTING IFR bit 6
    \ even while it is disabled. Testing the flag alone therefore serviced
    \ the bass on the back of every OTHER interrupt - so mute did not
    \ silence it, and an edge appeared at the same offset into every
    \ frame, right after the music. `lda IFR : and IER` is the idiom, and
    \ it is what vgcplayer_bass.asm does.
    lda USR_IFR
    and USR_IER
    sta via_pending

    and #IFR_T1                     \ the bass square wave. bass_irq uses
    beq no_bass                     \ only A, so nothing to save
    jsr bass_irq
.no_bass

    lda via_pending
    and #IFR_T2                     \ the raster point: time for the music
    beq no_music
    lda USR_T2CL                    \ reading it clears the timer's flag

    \ A song is authored for a fixed replay rate, and the AKL and AKY
    \ exports DO NOT CARRY IT - the player replays as often as it is
    \ called. Most Arkos songs are 50 Hz; Targhan's Dead On Time is 25,
    \ and calling it every field played it at exactly double speed, in
    \ tune, with nothing to show for it. example/build.py reads the rate
    \ out of the song and sets REPLAY_DIV.
    dec field_count
    bne no_music
    lda #REPLAY_DIV
    sta field_count

    txa : pha
    tya : pha
    lda #6 : jsr band               \ red: the band starts here
    jsr music_frame
    lda #7 : jsr band               \ black: and it ends here
    pla : tay
    pla : tax
.no_music

    lda SYS_IFR
    and #2                          \ System VIA, VSync: arm the raster
    beq chain
    sta SYS_IFR                     \ clear it
    lda #LO(RASTER_DELAY) : sta USR_T2CL
    lda #HI(RASTER_DELAY) : sta USR_T2CH    \ writing the high byte starts it
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
\ even entries are not the set either). A 4-colour mode needs four
\ writes per colour and a 16-colour mode one.
\ Unrolled, and the logical number walks 0,1,3,2,6,7,5,4 - GRAY CODE,
\ so consecutive entries differ in exactly one bit and each step is a
\ single EOR. All eight of 0-7 get written, order does not matter, and
\ it costs 46 cycles instead of the loop's ~200.
.band
{
    sta &FE21                       \ logical 0
    eor #&10 : sta &FE21            \ 1
    eor #&20 : sta &FE21            \ 3
    eor #&10 : sta &FE21            \ 2
    eor #&40 : sta &FE21            \ 6
    eor #&10 : sta &FE21            \ 7
    eor #&20 : sta &FE21            \ 5
    eor #&10 : sta &FE21            \ 4
    rts
}

\ silence: the four volume-off writes. It lives in ay2sn.asm and is not
\ AKL-specific, despite the name it arrived with.
.silence
    jmp akl_silence

.cursor_off
    EQUB 23, 1, 0, 0, 0, 0, 0, 0, 0, 0

.banner
IF PLAYER_AKY
    EQUS 13, 10, 13, 10, "Arkos Tracker AKY replay", 13, 10
ELSE
    EQUS 13, 10, 13, 10, "Arkos Tracker AKL replay", 13, 10
ENDIF
    EQUS "for the BBC Micro", 13, 10
    EQUS 13, 10, SONG_TITLE, 13, 10
    EQUS 13, 10, "The red band is the music.", 13, 10
    EQUS "Bass: ", 13, 10
    EQUS 13, 10, "SPACE mutes.  B cycles the bass.", 13, 10
    EQUS "ESCAPE quits.", 13, 10
    EQUB 0

\ The status text sits at the end of the "Bass: " line. VDU 31 is
\ TAB(x,y); the line is row 9 and the text is 6 characters in.
.bass_at    EQUB 31, 6, 8
.bass_names EQUS "OFF  "  \ five characters each, and the printer writes a
            EQUS "SOFT "  \ fixed five, so they are padded rather than
            EQUS "NOISE"  \ terminated

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
GUARD &6000                     \ MODE 6's screen starts here
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
