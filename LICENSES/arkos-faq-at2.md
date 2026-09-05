# The Arkos Tracker licence, as stated on the website

Arkos Tracker 2 shipped no LICENSE file. Its terms were given only in the
project FAQ, and this is that text, archived because the AT2-era sources
vendored in `reference/` are covered by it and nothing else states it.

Source: <https://www.julien-nevo.com/arkostracker/index.php/faq/>
Retrieved: 2026-09-05

> **Is it an open-source project?**
>
> Yes.

> **Can I use the players in my production?**
>
> Of course! The players are MIT-licensed. Basically, you can use and modify
> them at will, in any production, free or sold, open or closed source.
>
> One nice (but non-mandatory) thing you can do would be to put a credit
> somewhere in your production about Arkos Tracker 3, and we'll be best
> friends forever.

Arkos Tracker 3 ships `LICENSE.txt` — reproduced here as
`arkos-tracker3.txt` — which states the same MIT terms formally, with
"Copyright (c) 2016-2025 Julien Nevo".

Note the scope: the statement covers **the players**. It says nothing about
the `SongTo*.exe` exporters, so this repository does not redistribute them;
`tools/export_akl.py` and `example/build.py` require an Arkos install and
take the path from the environment.
