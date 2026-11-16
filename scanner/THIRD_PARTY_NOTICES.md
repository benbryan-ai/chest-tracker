# Third-party notices

`chest-scan` is built from MIT-licensed work by others:

- **ChestCounter** by LED-N (https://github.com/LED-N) — the replay analysis in `src/engine/`
  and the patched parser in `lib/`. Licence: `LICENSE-ChestCounter`.
- **FortniteReplayDecompressor** by Shiqan and contributors — the replay parser in `lib/`
  (patched by ChestCounter, see `lib/PATCHES.md`). Licence: `lib/LICENSE-FortniteReplayDecompressor`.

The treasure hunt data (`content.json`, bundled as `assets/content.json` and refreshed from the ChestCounter
repository) is also part of ChestCounter and covered by the same licence.

Both licences require their copyright notice and permission text to stay with copies of the code.
