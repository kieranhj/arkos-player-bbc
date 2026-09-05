# Taking this somewhere else

## To another 6502 with a real AY

`lib/aklplayer.asm` and `lib/akyplayer.asm` contain no BBC-specific code.
They fill `ay_regs` and stop. To drive a real AY instead of the SN76489,
replace `lib/ay2sn.asm` with fourteen register writes and keep everything
else — the players do not change at all.

`akyplayer.asm` is a port of a player that did exactly that, so if you are on
an Apple II, an Oric or an Atari you should use Arkos's own version rather
than this one: `reference/PlayerAky_atari_mads.asm` and
`reference/PlayerAKY_apple_oric_acme.a`. They are faster, being able to write
the chip directly.

## The one change worth understanding

The Atari AKY player writes each register as it computes it:

```
lda #reg   : sta AYR
lda value  : sta AYD
```

Here every such pair became `sta ay_sel` / `jsr ay_put`, and `ay_put` is the
whole hardware layer:

```
.ay_put
{
    stx ay_xtmp
    ldx ay_sel
    sta ay_regs,x
    ldx ay_xtmp
    rts
}
```

That is about 19 cycles a write against the Atari's 8, on a dozen or so
writes a frame. It buys a **mechanically faithful** port: the decode is byte
for byte the Atari's, which is what lets it be checked against Arkos's own
player output. Folding the register number into a direct store per site would
save a few hundred cycles a frame — do it if you need them, and re-run
`tools/verify/verify.py` afterwards.

## To AKM

AKM is the format to port next: 3,654 bytes against AKL's 4,741 for the same
tune, upstream-supported, and **no 6502 player exists anywhere**. Arkos's Z80
player and format documentation are in an Arkos Tracker 3 install
(`players/playerAkm/`), and `reference/AKM.md` is the spec.

Take the same route this project took for AKL, in this order, because it is
the order that catches mistakes early:

1. Transcribe the Z80 into Python first and check it against
   `SongToYm.exe`'s register log for the same song. Debugging a format
   misunderstanding in 6502 is much harder than in Python.
2. Write the 6502 against that reference, frame for frame.
3. Only then put it on a disc.

`tools/verify/verify.py` already has the shape for a third player: add the
export, add the entry point, and the harness does the rest.

Note that AKM shares AKL's envelope limitation — only shapes 8 and 0xa — so
whatever `ENV_BASE` does for AKL, an AKM player will need too.

## Multiple PSGs

Every Arkos AKY player is single-PSG, this one included, and a BBC has one
sound chip. `verify.py` and `example/build.py` read the channel count out of
the AKY header and refuse a six-channel song with an explanation rather than
playing half of it. See `songs/README.md`.

## The AKY header

The AKY binary does not start with the linker, and the player wants the
linker. The header is one flags byte, one channel-count byte, then a
four-byte PSG frequency **per PSG** — so six bytes for a three-channel song
and ten for a six-channel one. Arkos's own testers dodge this by using the
source export and its labels; a binary export has to compute it.

Getting it wrong does not fail. The player reads the PSG frequency as a
linker entry and plays convincing nonsense — silent channels, period 1 —
which is exactly what it did here first time.
