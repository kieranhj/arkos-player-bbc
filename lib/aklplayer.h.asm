\ ******************************************************************
\ * aklplayer.h.asm - the zero page lib/aklplayer.asm needs.
\ *
\ * INCLUDE this inside your own zero page block, at whatever address
\ * suits you; the player takes 22 consecutive bytes and does not care
\ * where they are.
\ *
\ * These are the player's WORKING POINTERS only. Everything else it
\ * keeps - the per-channel state, the note table, the register file -
\ * is absolute, declared at the end of aklplayer.asm and living
\ * wherever you assembled the player. Only the indirect reads have to
\ * be down here.
\ *
\ * The API is three symbols:
\ *
\ *   akl_init   A/X = lo/hi of the song, Y = subsong index
\ *   akl_play   one frame; fills ay_regs
\ *   ay_regs    14 bytes, the AY-3-8912 register file (in ay2sn.asm)
\ *
\ * ay_regs is the library's boundary. akl_play knows nothing about
\ * the BBC; lib/ay2sn.asm turns those fourteen bytes into SN76489
\ * writes. See docs/ay-to-sn.md.
\ ******************************************************************

.ptr            skip 2      ; the track / linker pointer being read
.iptr           skip 2      ; the instrument pointer being read
.tptr           skip 2      ; scratch indirect: the table lookups
.cell           skip 1      ; the byte being decoded
.iofs           skip 1      ; Y, parked while Y is needed for a table
.per            skip 2      ; the period being computed
.tmp            skip 2
.mixer          skip 1      ; R7 as the three channels build it up
.akl_tick       skip 1      ; ticks until the next line
.akl_speed      skip 1
.akl_height     skip 1      ; lines left in this pattern
.akl_prevh      skip 1      ; the height to reuse when a pattern does not say
.lnk            skip 2      ; the linker pointer
.jvec           skip 2      ; the effect dispatch vector
