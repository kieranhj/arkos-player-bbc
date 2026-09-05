\ ******************************************************************
\ * akyplayer.h.asm - the zero page lib/akyplayer.asm needs.
\ *
\ * INCLUDE this inside your own zero page block. The player takes 25
\ * CONSECUTIVE bytes and THE ORDER MATTERS: it indexes across these
\ * variables (`sta aky_c1_wait,y`, `sta aky_c1_track-2,y`,
\ * `lda aky_c1_prb,y` with y = 0/3/6). Do not reorder or insert.
\ *
\ * The API is three symbols:
\ *
\ *   aky_init   A/X = lo/hi of the song's subsong linker
\ *   aky_play   one frame; fills ay_regs
\ *   ay_regs    14 bytes, the AY-3-8912 register file (in ay2sn.asm)
\ ******************************************************************

.aky_block      skip 2      ; -> the register block being read
.aky_token      skip 1      ; the byte being decoded
.aky_linker     skip 2      ; -> the linker
.aky_patfc      skip 2      ; frames left in this pattern

.aky_c1_wait    skip 1      ; frames until this channel's next block
.aky_c1_prb     skip 2      ; -> its register block
.aky_c2_wait    skip 1
.aky_c2_prb     skip 2
.aky_c3_wait    skip 1
.aky_c3_prb     skip 2

.aky_c1_track   skip 2      ; -> its track
.aky_c2_track   skip 2
.aky_c3_track   skip 2

.aky_c1_state   skip 1      ; bit 0 = the next block is an INITIAL state
.aky_c2_state   skip 1
.aky_c3_state   skip 1
