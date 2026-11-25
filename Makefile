# Wrapper so that `make` works from PowerShell / Windows Terminal.
# GNU make runs recipes with cmd.exe here (no sh on PATH).
# Needs beebasm (..\..\Bin, or bin\ if present), Python 3 with py65 and numpy,
# and Arkos Tracker 3 (ARKOS3_HOME, default ~\OneDrive\Retro\Trackers\ArkosTracker3).
.PHONY: all build extra verify help
all: build

build:
	py -3 example\build.py

extra:
	py -3 example\build.py --extra

verify:
	py -3 tools\verify\verify.py --player akl
	py -3 tools\make_tables.py --check

help:
	@echo make        - build build\ARKOS-AKL/-AKY/-AKM .SSD (example\build.py)
	@echo make extra  - also ARKOS-EDGEA.SSD and ARKOS-ORION.SSD
	@echo make verify - verify.py --player akl and make_tables.py --check
	@echo make help   - this list (more commands in CLAUDE.md "Build and verify")
