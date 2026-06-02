from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

TEXT_EXTENSIONS = {
    ".asp",
    ".aspx",
    ".bat",
    ".c",
    ".cmd",
    ".config",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".h",
    ".hpp",
    ".htm",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".log",
    ".md",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".sql",
    ".sln",
    ".ts",
    ".tsx",
    ".txt",
    ".vb",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}

DEFAULT_EXCLUDES = {
    ".git",
    ".hg",
    ".svn",
    ".vs",
    ".vscode",
    "__pycache__",
    "bin",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "obj",
    "packages",
    "target",
    "vendor",
}

UTF8_ENCODINGS = {"utf-8", "utf-8-sig"}
NON_CONVERTIBLE_ENCODINGS = {"binary", "unknown"}
UTF_ENCODINGS_WITH_BOM_CHAR = {"utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"}
DETECT_CANDIDATES = (
    ("cp950", "utf8_failed_cp950_valid"),
    ("big5", "utf8_failed_big5_valid"),
    ("shift_jis", "utf8_failed_shift_jis_valid"),
    ("cp932", "utf8_failed_cp932_valid"),
    ("euc_jp", "utf8_failed_euc_jp_valid"),
    ("euc_kr", "utf8_failed_euc_kr_valid"),
    ("gbk", "utf8_failed_gbk_valid"),
    ("gb18030", "utf8_failed_gb18030_valid"),
    ("cp1252", "utf8_failed_cp1252_valid"),
    ("latin_1", "utf8_failed_latin1_valid"),
)


def list_windows_drives() -> list[dict[str, Any]]:
    drives: list[dict[str, Any]] = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(f"{letter}:\\")
        if root.exists():
            drives.append({"name": f"{letter}:\\", "path": str(root), "isDrive": True})
    return drives


@dataclass
class FileReport:
    path: str
    relative_path: str
    encoding: str
    confidence: str
    note: str
    size: int
    modified: float
    line_ending: str
    bom: str
    risk: str
    selectable: bool


def parse_csvish(value: str | None) -> list[str]:
    if not value:
        return []
    normalized = value.replace(";", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def normalize_encoding(name: str) -> str:
    key = name.strip().lower().replace("_", "-")
    aliases = {
        "big5": "cp950",
        "cp950": "cp950",
        "utf8": "utf-8",
        "utf-8": "utf-8",
        "utf8-bom": "utf-8-sig",
        "utf-8-bom": "utf-8-sig",
        "utf-8-sig": "utf-8-sig",
        "utf16": "utf-16",
        "utf-16": "utf-16",
        "utf16-le": "utf-16-le",
        "utf-16-le": "utf-16-le",
        "utf16-be": "utf-16-be",
        "utf-16-be": "utf-16-be",
        "utf32": "utf-32",
        "utf-32": "utf-32",
        "utf32-le": "utf-32-le",
        "utf-32-le": "utf-32-le",
        "utf32-be": "utf-32-be",
        "utf-32-be": "utf-32-be",
        "gb18030": "gb18030",
        "gbk": "gbk",
        "shift-jis": "shift_jis",
        "shift_jis": "shift_jis",
        "sjis": "shift_jis",
        "cp932": "cp932",
        "euc-jp": "euc_jp",
        "euc_jp": "euc_jp",
        "euc-kr": "euc_kr",
        "euc_kr": "euc_kr",
        "cp1252": "cp1252",
        "windows-1252": "cp1252",
        "latin1": "latin_1",
        "latin-1": "latin_1",
        "iso-8859-1": "latin_1",
        "auto": "auto",
    }
    return aliases.get(key, key)


def is_convertible_encoding(encoding: str, confidence: str) -> bool:
    return encoding not in UTF8_ENCODINGS | NON_CONVERTIBLE_ENCODINGS and confidence != "low"


def read_bytes(path: Path, max_bytes: int | None = None) -> bytes:
    with path.open("rb") as handle:
        return handle.read(max_bytes) if max_bytes else handle.read()


def is_probably_binary(data: bytes) -> bool:
    if not data:
        return False
    if b"\x00" in data[:4096]:
        return True
    control = sum(1 for b in data[:4096] if b < 9 or (13 < b < 32))
    return control / max(1, min(len(data), 4096)) > 0.08


def detect_line_ending(data: bytes) -> str:
    crlf = data.count(b"\r\n")
    lone_lf = data.count(b"\n") - crlf
    lone_cr = data.count(b"\r") - crlf
    if crlf and not lone_lf and not lone_cr:
        return "CRLF"
    if lone_lf and not crlf and not lone_cr:
        return "LF"
    if lone_cr and not crlf and not lone_lf:
        return "CR"
    if crlf or lone_lf or lone_cr:
        return "mixed"
    return "none"


def decode_strict(data: bytes, encoding: str) -> str | None:
    try:
        return data.decode(encoding, errors="strict")
    except UnicodeDecodeError:
        return None


def detect_utf16_without_bom(data: bytes) -> tuple[str, str] | None:
    if len(data) < 4 or len(data) % 2:
        return None

    even = data[0::2]
    odd = data[1::2]
    even_null_ratio = even.count(0) / len(even)
    odd_null_ratio = odd.count(0) / len(odd)
    if odd_null_ratio > 0.35 and even_null_ratio < 0.10 and decode_strict(data, "utf-16-le") is not None:
        return "utf-16-le", "utf16le_null_pattern"
    if even_null_ratio > 0.35 and odd_null_ratio < 0.10 and decode_strict(data, "utf-16-be") is not None:
        return "utf-16-be", "utf16be_null_pattern"
    return None


def looks_like_text(text: str) -> bool:
    if not text:
        return True
    sample = text[:4096]
    control = sum(1 for char in sample if ord(char) < 32 and char not in "\t\r\n")
    return control / len(sample) <= 0.02


def detect_utf16_by_text_shape(data: bytes) -> tuple[str, str] | None:
    if len(data) < 4 or len(data) % 2 or b"\x00" not in data[:4096]:
        return None
    for encoding in ("utf-16-le", "utf-16-be"):
        text = decode_strict(data, encoding)
        if text is not None and looks_like_text(text.removeprefix("\ufeff")):
            return encoding, f"{encoding.replace('-', '')}_text_shape"
    return None


def detect_encoding(path: Path, data: bytes) -> tuple[str, str, str, str]:
    if data.startswith(b"\xff\xfe\x00\x00"):
        return "utf-32-le", "certain", "bom", "UTF-32 LE BOM"
    if data.startswith(b"\x00\x00\xfe\xff"):
        return "utf-32-be", "certain", "bom", "UTF-32 BE BOM"
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", "certain", "bom", "UTF-8 BOM"
    if data.startswith(b"\xff\xfe"):
        return "utf-16-le", "certain", "bom", "UTF-16 LE BOM"
    if data.startswith(b"\xfe\xff"):
        return "utf-16-be", "certain", "bom", "UTF-16 BE BOM"
    utf16 = detect_utf16_without_bom(data)
    if utf16 is not None:
        encoding, note = utf16
        return encoding, "medium", note, "none"
    utf16 = detect_utf16_by_text_shape(data)
    if utf16 is not None:
        encoding, note = utf16
        return encoding, "medium", note, "none"
    if is_probably_binary(data):
        return "binary", "certain", "binary_signature", "none"

    if decode_strict(data, "utf-8") is not None:
        return "utf-8", "high", "valid_utf8", "none"

    for candidate, note in DETECT_CANDIDATES:
        text = decode_strict(data, candidate)
        if text is not None:
            if "\ufffd" in text:
                return candidate, "low", f"{candidate}_contains_replacement", "none"
            return candidate, "medium", note, "none"

    return "unknown", "low", "no_strict_decoder_matched", "none"


def detect_file(root: Path, path: Path) -> FileReport:
    stat = path.stat()
    data = read_bytes(path)
    encoding, confidence, note, bom = detect_encoding(path, data)
    risk = "low"
    selectable = is_convertible_encoding(encoding, confidence)
    if encoding in {"unknown", "binary"}:
        risk = "high"
        selectable = False
    elif confidence == "low":
        risk = "medium"
        selectable = False
    return FileReport(
        path=str(path),
        relative_path=str(path.relative_to(root)),
        encoding=encoding,
        confidence=confidence,
        note=note,
        size=stat.st_size,
        modified=stat.st_mtime,
        line_ending=detect_line_ending(data),
        bom=bom,
        risk=risk,
        selectable=selectable,
    )


def should_include(path: Path, include_patterns: list[str]) -> bool:
    if not include_patterns:
        return path.suffix.lower() in TEXT_EXTENSIONS
    return any(path.match(pattern) or path.name.lower().endswith(pattern.lower().lstrip("*")) for pattern in include_patterns)


def should_exclude(path: Path, root: Path, excludes: set[str]) -> bool:
    parts = set(part.lower() for part in path.relative_to(root).parts)
    return bool(parts & set(item.lower() for item in excludes))


def scan_files(payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(payload.get("root", "")).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("Root path does not exist or is not a directory.")

    include = parse_csvish(payload.get("include"))
    extra_exclude = set(parse_csvish(payload.get("exclude")))
    excludes = DEFAULT_EXCLUDES | extra_exclude
    recursive = bool(payload.get("recursive", True))
    max_size_mb = float(payload.get("maxSizeMb") or 5)
    max_size = int(max_size_mb * 1024 * 1024)

    candidates = root.rglob("*") if recursive else root.glob("*")
    reports: list[FileReport] = []
    skipped: list[dict[str, Any]] = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            if should_exclude(path, root, excludes):
                continue
            if not should_include(path, include):
                continue
            size = path.stat().st_size
            if size > max_size:
                skipped.append({"path": str(path), "reason": "max_size", "size": size})
                continue
            reports.append(detect_file(root, path))
        except (OSError, UnicodeError, ValueError) as exc:
            skipped.append({"path": str(path), "reason": str(exc), "size": 0})

    counts: dict[str, int] = {}
    for report in reports:
        counts[report.encoding] = counts.get(report.encoding, 0) + 1

    csv_path = APP_DIR / "encoding-report.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(reports[0]).keys()) if reports else ["path"])
        writer.writeheader()
        for report in reports:
            writer.writerow(asdict(report))

    return {
        "root": str(root),
        "files": [asdict(report) for report in reports],
        "counts": counts,
        "skipped": skipped,
        "reportPath": str(csv_path),
    }


def browse_directories(payload: dict[str, Any]) -> dict[str, Any]:
    raw_path = str(payload.get("path") or "").strip()
    if not raw_path:
        return {"path": "", "parent": "", "directories": list_windows_drives()}

    current = Path(raw_path).expanduser().resolve()
    if not current.exists() or not current.is_dir():
        raise ValueError("Directory does not exist.")

    directories: list[dict[str, Any]] = []
    for child in current.iterdir():
        try:
            if child.is_dir():
                directories.append({"name": child.name, "path": str(child), "isDrive": False})
        except OSError:
            continue

    directories.sort(key=lambda item: item["name"].lower())
    parent = str(current.parent) if current.parent != current else ""
    return {"path": str(current), "parent": parent, "directories": directories}


def decode_for_preview(path: Path, encoding: str) -> tuple[str, str]:
    data = read_bytes(path)
    actual = normalize_encoding(encoding)
    if actual == "auto":
        actual, _, _, _ = detect_encoding(path, data)
    if actual in {"binary", "unknown"}:
        raise ValueError(f"Cannot decode {actual} file.")
    text = data.decode(actual, errors="strict")
    if actual in UTF_ENCODINGS_WITH_BOM_CHAR:
        text = text.removeprefix("\ufeff")
    return text, actual


def preview_conversion(payload: dict[str, Any]) -> dict[str, Any]:
    path = Path(payload.get("path", "")).resolve()
    if not path.exists() or not path.is_file():
        raise ValueError("File does not exist.")
    from_encoding = normalize_encoding(payload.get("fromEncoding") or "auto")
    to_encoding = normalize_encoding(payload.get("toEncoding") or "utf-8")
    text, actual_from = decode_for_preview(path, from_encoding)
    encoded = text.encode(to_encoding, errors="strict")
    roundtrip = encoded.decode(to_encoding, errors="strict")
    sample_lines = [line for line in text.splitlines() if line.strip()][:12]
    return {
        "path": str(path),
        "fromEncoding": actual_from,
        "toEncoding": to_encoding,
        "sameTextAfterRoundtrip": text == roundtrip,
        "replacementCount": roundtrip.count("\ufffd"),
        "lineEnding": detect_line_ending(read_bytes(path)),
        "sizeBefore": path.stat().st_size,
        "sizeAfter": len(encoded),
        "sample": "\n".join(sample_lines[:12]),
        "risk": "low" if text == roundtrip and "\ufffd" not in roundtrip else "high",
    }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def target_path_for(source: Path, root: Path, output_root: Path) -> Path:
    return output_root / source.relative_to(root)


def convert_files(payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(payload.get("root", "")).resolve()
    files = [Path(item).resolve() for item in payload.get("files", [])]
    from_encoding = normalize_encoding(payload.get("fromEncoding") or "auto")
    to_encoding = normalize_encoding(payload.get("toEncoding") or "utf-8")
    mode = payload.get("mode") or "out"
    output_root = Path(payload.get("outputRoot") or (str(root) + "_utf8")).resolve()
    backup_root = Path(payload.get("backupRoot") or (str(root) + "_encoding_backup")).resolve()

    if not root.exists():
        raise ValueError("Root path does not exist.")
    if not files:
        raise ValueError("No files selected.")
    if mode not in {"out", "in-place"}:
        raise ValueError("Unknown convert mode.")

    results: list[dict[str, Any]] = []
    manifest: dict[str, Any] = {
        "root": str(root),
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "fromEncoding": from_encoding,
        "toEncoding": to_encoding,
        "mode": mode,
        "files": results,
    }

    if mode == "out":
        output_root.mkdir(parents=True, exist_ok=True)
    else:
        backup_root.mkdir(parents=True, exist_ok=True)

    for source in files:
        try:
            if not source.exists() or not source.is_file():
                raise ValueError("Missing file.")
            if root not in source.parents and source != root:
                raise ValueError("Selected file is outside scan root.")
            original = read_bytes(source)
            text, actual_from = decode_for_preview(source, from_encoding)
            if "\ufffd" in text:
                raise ValueError("Decoded text contains replacement characters.")
            converted = text.encode(to_encoding, errors="strict")
            converted.decode(to_encoding, errors="strict")

            if mode == "out":
                destination = target_path_for(source, root, output_root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(converted)
                backup = ""
            else:
                backup = str(target_path_for(source, root, backup_root))
                backup_path = Path(backup)
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, backup_path)
                source.write_bytes(converted)
                destination = source

            results.append(
                {
                    "path": str(source),
                    "destination": str(destination),
                    "backup": backup,
                    "status": "success",
                    "from": actual_from,
                    "to": to_encoding,
                    "sha256Before": sha256_bytes(original),
                    "sha256After": sha256_bytes(converted),
                    "sizeBefore": len(original),
                    "sizeAfter": len(converted),
                }
            )
        except Exception as exc:
            results.append({"path": str(source), "status": "failed", "error": str(exc)})

    manifest_path = (output_root if mode == "out" else backup_root) / "encoding-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "results": results,
        "manifestPath": str(manifest_path),
        "success": sum(1 for item in results if item.get("status") == "success"),
        "failed": sum(1 for item in results if item.get("status") == "failed"),
    }


class AppHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), format % args))

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def parse_payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        request_path = self.path.split("?", 1)[0]
        if request_path == "/":
            self.send_file(STATIC_DIR / "index.html")
            return
        static_path = (STATIC_DIR / request_path.lstrip("/")).resolve()
        if STATIC_DIR in static_path.parents:
            self.send_file(static_path)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            payload = self.parse_payload()
            if self.path == "/api/scan":
                self.send_json(scan_files(payload))
            elif self.path == "/api/browse":
                self.send_json(browse_directories(payload))
            elif self.path == "/api/preview":
                self.send_json(preview_conversion(payload))
            elif self.path == "/api/convert":
                self.send_json(convert_files(payload))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)


def main() -> None:
    parser = argparse.ArgumentParser(description="Encoding Inspector UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Encoding Inspector UI running at http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
