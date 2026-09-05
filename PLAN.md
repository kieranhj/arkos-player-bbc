# arkos-player-bbc — what is left

**Three players, all verified; three demo discs, all booting.** As of
2026-09-05 the library does what it was built to do. What follows is only the
work that has not been done.

- [`docs/history.md`](docs/history.md) — how it got built, and what the plan
  got wrong on the way
- [`docs/decisions.md`](docs/decisions.md) — KC's decisions, binding
- `README.md` — what it is, the measured tables, the API

Each item below has an acceptance test. Nothing is believed without one.

---

## 1. Listening

**Not done, and it is the point of all of it.** Every check so far compares
registers; none of them says whether the tune sounds right.

```
python tools/verify/verify.py --player akm --song X.aks --bass 2 --snf build/x.snf
python tools/sn2wav.py build/x.snf -o build/x.wav
```

against Arkos's own `SongToWav.exe` render of the same song.

*Accepts when*: KC has listened to all three players side by side with the
Arkos render, and any difference that matters is either fixed or written down
in [`docs/fidelity-plan.md`](docs/fidelity-plan.md).

## 2. The fidelity work still open

All of it lives in `lib/ay2sn.asm`, so it benefits every player at once. The
replays are already exact; what is wrong is the conversion to a chip the music
was not written for. [`docs/fidelity-plan.md`](docs/fidelity-plan.md) has the
measurements and the options.

- **The drums are 4–6 dB too loud.** `ym2sn.py` mixes the noise at a share of
  each open channel's amplitude; we take the loudest whole. Independent of any
  player.
- **The hardware envelope** (E2/E3). It is all that EDGEA's residual is.
- **A second and third bass voice.** There is one, and it is sticky. Over the
  75-song corpus **56 songs want more than one**: 30 want three simultaneous
  voices and 26 want two.

*Accepts when*: each is either built and measured against `ym2sn.py` frame by
frame, or recorded in `fidelity-plan.md` as a decision not to.

## 3. The three AKM questions

All parked deliberately, all written up with reproduction steps in
[`docs/akm-open-questions.md`](docs/akm-open-questions.md). Neither blocks the
player, which is verified on the 39 songs in
`tools/verify/akm_known_good.txt`.

- **The rendering discrepancy**, 25 of the 64 CPC-clock corpus songs. Not a
  decode fault — that is ruled out by 48,201 checks against Arkos's own
  annotation. The two players disagree about which instrument cell is heard on
  which frame. Traced to the bottom on one song and not explained.
- **The eleven tunes with a different PSG clock** — nine at the Atari ST's
  2 MHz, two at the Spectrum's 1,773,400 Hz. Nothing in the player is
  CPC-specific: it is a second generated period table and a constant. It would
  reach a much bigger body of music, and exercise the bass work against
  material it has never seen.
- **SoftAndHard has still never executed.** Exactly one corpus song uses it,
  `Totta - Hardy (MSX)` — which runs at 1 MHz despite its name, so it is in
  the CPC corpus, and is one of the 25 above. The only route to testing that
  path runs through the first question.

*Accepts when*: the discrepancy is explained (or referred upstream); an ST
build verifies on the ST tunes the way the CPC build does on its 39; and
SoftAndHard has run.

## 4. edge-beeb takes `lib/` as a verbatim copy

Decision 4, not yet done. edge-beeb's `MUSIC_AKL` build still carries its own
copy of the player; this library is upstream and edge-beeb should never edit
it — the same treatment edge-beeb's own `lib/vgiplayer.asm` already gets.

*Accepts when*: edge-beeb's `lib/aklplayer.asm` is byte-identical to this
repo's, its build still assembles, and `PROVENANCE.md` there says where it
came from.

## 5. Write to Targhan

Not done. There is more to say now than when it was first noted:

- to thank him — none of this exists without Arkos Tracker and his format
  documentation;
- to confirm the demo-tune choice (*Dead On Time*, *Crtc*) is welcome;
- **AT2's AKL exporter emits data no player can play** — tracks referencing
  arpeggio table 29 when ten were written ([`docs/format-akl.md`](docs/format-akl.md));
- **AT2's and AT3's `SongToYm.exe` disagree** about the same song, by far more
  than a rounding tolerance ([`docs/verification.md`](docs/verification.md));
- **Arkos Tracker 3 ships a V0 AKM player and a V1 AKM exporter**, and the
  exporter's output contains instrument data AT3's own replay does not play
  ([`docs/format-akm.md`](docs/format-akm.md)). This is the one he will most
  want to know.

*Accepts when*: sent.

---

## Not planned, but the obvious next thing

**AKG has no 6502 player anywhere**, and it is the only Arkos format left
without one. It carries the true envelope shape, so it needs no `ENV_BASE`
compensation at all — which would close the one fidelity gap AKL and AKM
share. [`docs/porting.md`](docs/porting.md) is the route, and it says what to
do differently: build the annotation oracle first, not last.
