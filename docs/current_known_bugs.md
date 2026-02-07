# Current Known Bugs

Bugs discovered during MTGO support implementation (2026-02-07). All three have been fixed.

## Fixed

### 1. Byte vs character offset mismatch in MtgoScanner (CRITICAL)
- **File:** `src/mtgo_scanner.py` — `__parse_header()`
- **Issue:** `self.search_offset = len(content.encode('utf-8'))` computed a byte offset, but `f.seek()` in text mode expects a character position. For any draft log containing non-ASCII characters (e.g., accented card names like "Lórién Revealed"), the offset would overshoot, causing content to be skipped or re-read on the next incremental parse.
- **Fix:** Changed to `self.search_offset = len(content)` (character count).

### 2. `set_arena_file` semantic mismatch in MtgoScanner (IMPORTANT)
- **File:** `src/mtgo_scanner.py` — `set_arena_file()`
- **Issue:** The overlay's "Open Log" menu calls `self.draft.set_arena_file(filename)` with a file path. MtgoScanner blindly assigned this to `self.log_folder`, which should be a directory. This broke folder scanning since `os.listdir()` fails on a file path.
- **Fix:** Added a check: if the input is a directory, use it directly; otherwise, extract the parent directory with `os.path.dirname()`.

### 3. Unconditional MTGO polling in overlay (IMPORTANT)
- **File:** `src/overlay.py` — `__arena_log_check()`
- **Issue:** The MTGO branch called `__update_overlay_callback(True)` every 1000ms regardless of whether anything changed. This triggered `draft_start_search()` (folder scan) and `draft_data_search()` (file read) plus full UI widget updates on every tick.
- **Fix:** Added mtime guard matching the Arena polling pattern. Checks `max(folder_mtime, file_mtime)` — folder mtime detects new draft files, file mtime detects content growth. Only triggers an update when the timestamp changes.
