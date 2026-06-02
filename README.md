# Encoding Guardian UI

Local web UI for scanning text file encodings, previewing conversions, and converting non-UTF-8 text files to UTF-8 or UTF-8 with BOM safely.

## Run

Create a desktop shortcut:

```powershell
.\install-shortcut.ps1
```

Double-click:

```text
run.bat
```

Or from PowerShell:

```powershell
.\run.ps1
```

Manual command:

```powershell
python server.py --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000/
```

Remove the desktop shortcut:

```powershell
.\uninstall-shortcut.ps1
```

## Features

- Scan a selected directory path with include/exclude filters.
- Detect UTF-8, UTF-8 BOM, UTF-16 BOM, CP950/Big5, binary, and unknown files.
- Filter Big5/CP950, non-UTF-8, unknown, low confidence, or convertible files.
- Preview one file before conversion.
- Convert selected non-UTF-8 text files to UTF-8 or UTF-8 with BOM (`utf-8-sig`).
- Output to a new directory or convert in place with backup.
- Generate a conversion manifest.

The tool defaults to conservative behavior: unknown files and low-confidence files are not selected automatically.
