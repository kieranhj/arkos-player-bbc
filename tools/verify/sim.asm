\ ******************************************************************
\ * sim.asm - the real lib/ sources, standalone, for tools/verify/verify.py
\ * to run in a 6502 simulator.
\ *
\ * It INCLUDEs the REAL sources, not copies, so what is verified is
\ * what ships. Assemble from the REPO ROOT, because the library's own
\ * INCLUDEs are written relative to it:
\ *
\ *   beebasm -i tools/verify/sim.asm -D SIM_SONG=16384 -D PLAYER_AKY=0 \
\ *           -d -labels tools/verify/build/labels.txt
\ *
\ * PLAYER_AKY selects which replay is built around the shared ay2sn
\ * layer. Both fill ay_regs; ay2sn converts it. That is the whole
\ * architecture, and this file is the smallest demonstration of it.
\ ******************************************************************

ORG &70
IF PLAYER_AKY
INCLUDE "lib/akyplayer.h.asm"
ELSE
INCLUDE "lib/aklplayer.h.asm"
ENDIF

ORG &1100
GUARD &3f00
.start

\ The spine first, so nothing in a player is a forward reference.
INCLUDE "lib/ay2sn.asm"

IF PLAYER_AKY
INCLUDE "lib/akyplayer.asm"
ELSE
INCLUDE "lib/aklplayer.asm"
ENDIF

\ One frame of music: replay the tracker, then convert what it produced.
\ This is exactly what a host's VSync handler calls.
.music_frame
{
IF PLAYER_AKY
    jsr aky_play
ELSE
    jsr akl_play
ENDIF
    jmp ay2sn
}
.all_end

ORG SIM_SONG
.song_data
INCBIN "tools/verify/build/song.bin"
.song_end

SAVE "tools/verify/build/Sim", start, song_end, start
