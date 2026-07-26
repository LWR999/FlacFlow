# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

FlacFlow is a single-file Flask web app that automates FLAC music library metadata processing for a personal Roon Server setup. It scans a staging directory of downloaded albums, parses metadata from folder names, rewrites FLAC tags, embeds resized cover art, and moves albums through a Pre → Post → Library pipeline.

There is no test suite, build step, linter, or package manifest in this repo — it's a single production script (`flacflow.py`) plus documentation.

## Running

```bash
pip install flask mutagen pillow
python3 flacflow.py
```

Serves on `http://0.0.0.0:5000`. On startup it creates `flacflow_config.json` (from `DEFAULT_CONFIG` in `flacflow.py`) if one doesn't exist, plus the configured pre/post/library directories. There's no reload/dev-server flag — restart the process to pick up code changes.

Deployed in production as a systemd service (see `flacflow_deployment.md`); the live deployment path differs from this repo (`/home/dl/flacflow/`) and expects paths like `/home/dl/torrents/music/_Pre/` and a Drobo-mounted library.

## Architecture

Everything lives in `flacflow.py`: config, processing logic, and the Flask app (including the entire frontend as an inline `FULL_TEMPLATE` HTML/CSS/JS string rendered by `/`). There's no separate templates/static directory or JS bundler — edit the HTML/JS in-place inside the Python string.

**`FlacFlowProcessor`** (all core logic) is instantiated once as a module-level `processor` object at import time, and the Flask routes are thin wrappers around its methods.

### Pipeline stages

1. **Pre-processing** (`paths.pre_processing`): raw downloaded album folders land here. `scan_albums`/`analyze_album` inspect each folder (FLAC count, artwork, multi-disc structure, parsed metadata) without modifying anything, producing `status: ready|warning|duplicate` for the UI.
2. **Process** (`process_album` → `process_single_album` or `process_multidisc_album`): rewrites FLAC tags in place, embeds resized artwork, deletes cruft files, then `move_to_post_processing` renames the folder to `"Artist - Album"` and moves it into `_CD` or `_Hires` under `paths.post_processing`, based on bit depth parsed from the original folder name.
3. **Publish** (`publish_to_library`): moves a post-processed album into the final library, choosing `FLAC 16-Bit CD` or `FLAC 24-Bit HiRes` by checking whether the *current path* contains the hires folder name (not by re-inspecting the FLAC files).

### Metadata parsing (`parse_folder_name`)

Expects folder names shaped like:
```
{Artist} - {Album} ({Year}) [FLAC] [{BitDepth}B-{SampleRate}kHz] [{Genre}]
```
Artist/Album split on the *first* `" - "`. Genre comes from the last `[...]` bracket group; year from `(YYYY)`; bit depth/sample rate from a `[NNB-NN.NkHz]` bracket. `format_text` applies word capitalization plus configurable find/replace pairs (different lists for artist vs. album text — see `processing.artist_replacements` / `processing.album_replacements`), with special-cased lowercasing after apostrophes (e.g. "Don't").

### Multi-disc handling (`find_disc_folders`)

Any subdirectory whose name contains `disc`+digit or `cd`+digit (case-insensitive, quote-stripped) is treated as a disc folder and sorted by the first number found in its name. Disc/CD folder structure is preserved (not flattened) so Roon displays discs correctly — this is a deliberate design decision, not an oversight.

### Config

`DEFAULT_CONFIG` in `flacflow.py` is the schema; `flacflow_config.json` (git-ignored, created on first run) overrides it via a recursive dict merge (`merge_config`) — only keys present in the JSON override defaults, so partial configs are safe. Key sections: `paths` (pre/post/library), `artwork` (resize target, JPEG quality), `processing` (text replacement rules, disc patterns, files to keep/remove, folders to preserve), `output` (CD/Hi-Res subfolder names).

### Artwork

`process_artwork` picks `cover.jpg` if present (else first image file), resizes to `artwork.target_width`/`target_height` via Pillow, re-encodes as JPEG, embeds it into every FLAC file in the album via `update_flac_metadata`, and **deletes all original image files** after embedding. Post-processing artwork previews in the UI are extracted back out of the embedded FLAC picture data (`get_embedded_artwork`), since the source image files no longer exist at that point.

### API surface

All under `/api/`: `albums` (GET, scans pre-processing), `post-albums` (GET, scans post-processing), `artwork` / `embedded-artwork` (GET, serve images by filesystem path via query param — no path validation beyond `os.path.exists`), `process` / `delete` / `publish` (POST, take `{"album_path": ...}`).

There is no authentication — per `music_library_spec.md`, this is intentional and scoped to local-network-only use.
