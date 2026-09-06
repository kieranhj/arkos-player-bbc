"""Which corpus songs use an envelope shape AKL and AKM cannot encode?

AKL and AKM store ONE BIT of envelope shape, meaning ENV_BASE or ENV_BASE + 2
(see lib/aklplayer.asm and tools/arkos.py's envelope_base). AKG carries all
four bits, shapes 8 to 15. This reads the TRUE shapes out of SongToAkg.exe's
source export - the only place they are written down - and sorts the corpus
into three: no hardware envelope at all, shapes that fit one AKL/AKM pair, and
shapes that do not fit any pair.

What it caught: eight of the 75 songs use shapes no AKL or AKM export can
carry, two of them the one-shot envelopes 9 and 13 which have no pair at all;
and fifteen more need an ENV_BASE other than 8, which no export carries and a
host must be told. That is the measured case for an AKG player, and it is in
docs/porting.md.

The same sweep as survey_tunes.py: every song the Arkos install ships, this
repo's own, and EDGEA next door. Nothing is committed - the songs stay where
they are.

    python tools/survey_envelopes.py [extra songs...]
"""
import sys, os, glob, re, subprocess, tempfile, collections
sys.path.insert(0, 'tools')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import arkos

EXE = arkos.find(os.path.join(arkos.AT3, 'tools', 'SongToAkg.exe'),
                 os.path.join(arkos.AT2, 'tools', 'SongToAkg.exe'))
if not EXE:
    sys.exit('no SongToAkg.exe: set ARKOS3_HOME or ARKOS2_HOME')


def shapes(song):
    """The set of envelope shapes the song really uses, or None if it fails."""
    fd, tmp = tempfile.mkstemp(suffix='.asm')
    os.close(fd)
    try:
        # AT3's exporter takes -s; AT2's does not. Try it, then without.
        r = subprocess.run([EXE, '-s', '1', song, tmp], capture_output=True, text=True)
        if r.returncode != 0:
            r = subprocess.run([EXE, song, tmp], capture_output=True, text=True)
        if r.returncode != 0:
            return None
        text = open(tmp, encoding='utf-8', errors='replace').read()
    finally:
        try: os.remove(tmp)
        except OSError: pass
    return set(int(n) for n in re.findall(r'Envelope:\s*(\d+)', text))


songs = []
for d in ('songs/STarKos', 'songs/ArkosTracker2', 'songs/ArkosTracker3'):
    songs += sorted(glob.glob(os.path.join(arkos.AT3, d, '*.sks')) +
                    glob.glob(os.path.join(arkos.AT3, d, '*.aks')))
songs += sorted(glob.glob(os.path.join(ROOT, 'songs', '*.aks')))
EDGEA = os.path.join(os.path.dirname(ROOT), 'edge-beeb', 'source_cpc', 'Music', 'EDGEA.SKS')
if os.path.exists(EDGEA):
    songs.append(EDGEA)
songs += [a for a in sys.argv[1:] if os.path.exists(a)]

hist = collections.Counter()
none = fits = fail = 0
shifted, unencodable = [], []

for song in songs:
    used = shapes(song)
    name = os.path.basename(song)
    if used is None:
        fail += 1
        print('  EXPORT FAILED  %s' % name)
        continue
    if not used:
        none += 1
        continue
    for v in used:
        hist[v] += 1
    base = min(used) & ~1                   # the pair is (base, base + 2)
    if used <= {base, base + 2}:
        fits += 1
        if base != 8:
            shifted.append((name, sorted(used), base))
    else:
        unencodable.append((name, sorted(used)))

print('songs swept             : %d' % len(songs))
if fail:
    print('  export failed         : %d' % fail)
print('  no hardware envelope  : %d' % none)
print('  fits one AKL/AKM pair : %d' % fits)
print('  fits NO pair          : %d   <- only AKG can carry these'
      % len(unencodable))
print()
print('songs using each shape:')
for k in sorted(hist):
    print('  %2d : %d' % (k, hist[k]))
print()
print('need an ENV_BASE other than 8 (%d) - no export carries this:' % len(shifted))
for name, used, base in shifted:
    print('  %-50s %-12s ENV_BASE %d' % (name[:50], str(used), base))
print()
print('AKL and AKM cannot encode these at all (%d):' % len(unencodable))
for name, used in unencodable:
    print('  %-50s %s' % (name[:50], used))
