"""Sweep a corpus of Arkos songs and say what each one stresses.

Every song the Arkos install ships, plus this repo's own songs/ and Edge
Grinder's EDGEA - the tune the whole library was built for, and the one every
figure in the docs is quoted against, so it belongs in the comparison.

Writes build/tunes.md. Nothing here is committed: the Arkos songs stay in the
Arkos install and EDGEA stays in edge-beeb.

    python tools/survey_tunes.py [extra songs...]
"""
import sys, os, glob, subprocess, tempfile, collections
sys.path.insert(0,'tools'); sys.path.insert(0,'tools/verify')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import arkos
from verify import read_ym
AY=1000000.0; SN=4000000.0; FLOOR=SN/(32*1023)

# What the SN's three fixed noise rates sound at, and what our table picks
# against what ym2sn picks - the B1 work's step 1. See make_tables.py.
SN_NOISE=[SN/(32.0*16*(1<<r)) for r in range(3)]
OURS=[0]*8+[1]*8+[2]*16
YM2SN=[min(range(3),key=lambda r:abs(AY/(16.0*max(n,1))-SN_NOISE[r]))
       for n in range(32)]
AT3=arkos.AT3
EXE=arkos.song_to_ym_exe()

def stats(song):
    fd,tmp=tempfile.mkstemp(suffix='.ym'); os.close(fd)
    try:
        r=subprocess.run([EXE,'-p','1',song,tmp],capture_output=True,text=True)
        if r.returncode: return None
        n,cols=read_ym(tmp)
        _,clock,rate=arkos.ym_header(tmp)
    finally:
        try: os.remove(tmp)
        except OSError: pass
    env=0; below=0; audible=0; prev=None; hops=0; bassmax=0
    bass_f=0; bass_busy=0; two=0; two_free=0; noise_f=0; noise_diff=0
    for i in range(n):
        r=[cols[j][i] for j in range(14)]
        if any(r[8+c]&16 for c in range(3)): env+=1
        # is the noise AUDIBLE this call? open on a channel that has volume.
        busy=any((not (r[7]>>(3+c))&1) and (r[8+c]&31) for c in range(3))
        if busy:
            noise_f+=1
            if OURS[r[6]&31]!=YM2SN[r[6]&31]: noise_diff+=1
        low=[]
        for ch in range(3):
            if not (r[8+ch]&31): continue
            if (r[7]>>ch)&1: continue
            audible+=1
            p=r[2*ch]|((r[2*ch+1]&15)<<8)
            if p and AY/(16.0*p)<FLOOR: low.append(ch); below+=1
        bassmax=max(bassmax,len(low))
        if low:
            bass_f+=1
            if busy: bass_busy+=1      # B1 must yield: the drums win
            if len(low)>1:
                two+=1
                if not busy: two_free+=1
        f=low[0] if low else None
        if f is not None and prev is not None and f!=prev: hops+=1
        prev=f
    return dict(frames=n,rate=rate or 50,env=env,below=below,audible=audible,
                hops=hops,bassmax=bassmax,bass_f=bass_f,bass_busy=bass_busy,
                two=two,two_free=two_free,noise_f=noise_f,noise_diff=noise_diff)

def psgs(song):
    fd,tmp=tempfile.mkstemp(suffix='.bin'); os.close(fd)
    try:
        exe=os.path.join(AT3,'tools','SongToAky.exe')
        r=subprocess.run([exe,'-s','1','-bin','-adr','0x4000',song,tmp],
                         capture_output=True,text=True)
        if r.returncode: return 0
        return (open(tmp,'rb').read()[1]+2)//3
    finally:
        try: os.remove(tmp)
        except OSError: pass

songs=[]
for d in ('songs/STarKos','songs/ArkosTracker2','songs/ArkosTracker3'):
    songs += sorted(glob.glob(os.path.join(AT3,d,'*.sks'))+
                    glob.glob(os.path.join(AT3,d,'*.aks')))
# this repo's own songs, and EDGEA next door in the Edge Grinder port
songs += sorted(glob.glob(os.path.join(ROOT,'songs','*.aks')))
EDGEA = os.path.join(os.path.dirname(ROOT),'edge-beeb','source_cpc','Music','EDGEA.SKS')
if os.path.exists(EDGEA):
    songs.append(EDGEA)
songs += [a for a in sys.argv[1:] if os.path.exists(a)]
rows=[]
for s in songs:
    st=stats(s)
    if not st: continue
    st['psg']=psgs(s); st['name']=os.path.basename(s)
    rows.append(st)
    print('%-46s %2dHz env%3d%% bass%3d%% max%d  drums-block%3d%% 2v%3d%% rate-diff%3d%%'%(
        st['name'][:46],st['rate'],
        100*st['env']//max(st['frames'],1),
        100*st['below']//max(st['audible'],1),st['bassmax'],
        100*st['bass_busy']//max(st['bass_f'],1),
        100*st['two']//max(st['bass_f'],1),
        100*st['noise_diff']//max(st['noise_f'],1)))
with open('build/tunes.md','w') as f:
    f.write('# What each bundled Arkos song stresses\n\n')
    f.write('Not committed; the songs live in the Arkos install.\n\n')
    f.write('Columns for the periodic-noise bass (B1): **drums block** is the share\n'
            'of bass calls where the noise channel is audibly busy, so B1 must yield\n'
            'and the note octave-shifts; **2 voices** is the share of bass calls\n'
            'wanting two at once, and **free** the share of THOSE with the noise\n'
            'channel idle. **rate diff** is how often the old noise-rate table\n'
            'disagreed with ym2sn, before step 1 of the B1 work replaced it.\n\n')
    f.write('| song | rate | PSGs | calls | envelope | below 122 Hz | bass hops |'
            ' max voices | drums block | 2 voices | free | rate diff |\n')
    f.write('|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|\n')
    for r in sorted(rows,key=lambda r:-r['below']/max(r['audible'],1)):
        f.write('| %s | %d Hz | %d | %d | %d%% | %d%% | %d | %d | %d%% | %d%% | %d%% | %d%% |\n'%(
            r['name'],r['rate'],r['psg'],r['frames'],
            100*r['env']//max(r['frames'],1),
            100*r['below']//max(r['audible'],1),r['hops'],r['bassmax'],
            100*r['bass_busy']//max(r['bass_f'],1),
            100*r['two']//max(r['bass_f'],1),
            100*r['two_free']//max(r['two'],1),
            100*r['noise_diff']//max(r['noise_f'],1)))
print('\nbuild/tunes.md written, %d songs'%len(rows))
