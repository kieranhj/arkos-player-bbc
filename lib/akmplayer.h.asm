\ ******************************************************************
\ * akmplayer.h.asm - the zero page lib/akmplayer.asm needs.
\ *
\ * INCLUDE this inside your own zero page block, at whatever address
\ * suits you; the player takes 25 consecutive bytes and does not care
\ * where they are. (AKL takes 22, AKY 25.)
\ *
\ * These are the player's WORKING POINTERS and its loop counters only.
\ * Everything else it keeps - the per-channel state, the song header's
\ * table addresses, the register file - is absolute, declared at the
\ * end of akmplayer.asm and living wherever you assembled the player.
\ * Only what is read indirectly, or read every cell, is down here.
\ *
\ * The API is three symbols:
\ *
\ *   akm_init   A/X = lo/hi of the song, Y = subsong index
\ *   akm_play   one frame; fills ay_regs
\ *   ay_regs    14 bytes, the AY-3-8912 register file (in ay2sn.asm)
\ *
\ * ay_regs is the library's boundary. akm_play knows nothing about
\ * the BBC; lib/ay2sn.asm turns those fourteen bytes into SN76489
\ * writes. See docs/ay-to-sn.md.
\ *
\ * ENV_BASE IS THE HOST'S TO DEFINE, before it INCLUDEs the player.
\ * See the head of akmplayer.asm.
\ ******************************************************************

.ptr            skip 2      ; the track / linker pointer being read
.iptr           skip 2      ; the instrument pointer being read
.tptr           skip 2      ; scratch indirect: the table lookups
.per            skip 2      ; the period being computed
.tmp            skip 2
.lnk            skip 2      ; the linker pointer
.jvec           skip 2      ; the effect dispatch vector
.note_tbl       skip 2      ; the subsong's note table - read through, so ZP
.cell           skip 1      ; the byte being decoded
.iofs           skip 1      ; Y, parked while Y is needed for a table
.mixer          skip 1      ; R7 as the three channels build it up
.lflags         skip 1      ; the linker's state byte, shifted as it is read
.fxflag         skip 1      ; "this cell has effects", set while the cell is read
.akm_tick       skip 1      ; ticks until the next line
.akm_speed      skip 1
.akm_height     skip 1      ; lines left in this pattern
.akm_prevh      skip 1      ; the height to reuse when a pattern does not say
