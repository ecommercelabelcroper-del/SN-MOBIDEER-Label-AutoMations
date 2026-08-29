import http.server
import json
import csv
import os
import io
import subprocess
from urllib.parse import urlparse

# ── Self-locate: project folder = folder where bridge.py lives ──────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Read config.txt for user-configurable paths ─────────────────────
def read_config():
    cfg = {}
    cfg_file = os.path.join(BASE_DIR, "config.txt")
    if os.path.isfile(cfg_file):
        with open(cfg_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    cfg[key.strip()] = val.strip()
    return cfg

_cfg = read_config()

PORT = int(_cfg.get("PORT", 7788))

# BarTender EXE — from config, or auto-detect, or default
def find_bartender():
    # 1. From config.txt
    if "BARTENDER_EXE" in _cfg and _cfg["BARTENDER_EXE"] != "AUTO":
        p = _cfg["BARTENDER_EXE"]
        if os.path.isfile(p):
            return p
    # 2. Search common install locations
    candidates = [
        r"C:\Program Files\Seagull\BarTender 2022\bartend.exe",
        r"C:\Program Files\Seagull\BarTender 2021\bartend.exe",
        r"C:\Program Files\Seagull\BarTender 2020\bartend.exe",
        r"C:\Program Files (x86)\Seagull\BarTender 2022\bartend.exe",
        r"C:\Program Files (x86)\Seagull\BarTender 2021\bartend.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    # 3. Return default (will show error if not found)
    return r"C:\Program Files\Seagull\BarTender 2022\bartend.exe"

BARTENDER_EXE = find_bartender()

# BTW file — first look in project folder (portable), then old location
def find_btw():
    # 1. Project folder (recommended — copy BTW here)
    local_btw = os.path.join(BASE_DIR, "SN Labels.btw")
    if os.path.isfile(local_btw):
        return local_btw
    # 2. From config.txt
    if "BTW_FILEPATH" in _cfg and _cfg["BTW_FILEPATH"] != "AUTO":
        p = _cfg["BTW_FILEPATH"]
        if os.path.isfile(p):
            return p
    # 3. Old hardcoded location (fallback)
    old_path = os.path.join(os.environ.get("USERPROFILE","C:\\Users\\admin"),
                            "Documents","BarTender","BarTender Documents",
                            "Chote Labels","SN Labels.btw")
    return old_path

BTW_FILEPATH = find_btw()

# CSV for BarTender — always inside project folder (portable!)
CSV_FILENAME = os.path.join(BASE_DIR, "SN Label_Template_For_BarTender.csv")

# Master SKU database — always inside project folder
MASTER_FILE  = os.path.join(BASE_DIR, "Master_SKU_Database.csv")

# ── Startup log ─────────────────────────────────────────────────────
print("=" * 60)
print("  SN MOBIDEER Bridge — Path Check")
print("=" * 60)
print(f"  Project Folder : {BASE_DIR}")
print(f"  BarTender EXE  : {BARTENDER_EXE}")
print(f"    -> {'FOUND ✓' if os.path.isfile(BARTENDER_EXE) else 'NOT FOUND ✗  (install BarTender)'}")
print(f"  BTW File       : {BTW_FILEPATH}")
print(f"    -> {'FOUND ✓' if os.path.isfile(BTW_FILEPATH) else 'NOT FOUND ✗  (copy SN Labels.btw here)'}")
print(f"  Master DB      : {MASTER_FILE}")
print(f"    -> {'FOUND ✓' if os.path.isfile(MASTER_FILE) else 'Will be created on first use'}")
print(f"  CSV Output     : {CSV_FILENAME}")
print("=" * 60)

FIELDNAMES = ["SKU", "Model ID", "Month_Year_Manufacturing", "Brand_Color",
              "Country_of_Origin", "FSN", "Material"]


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


class BridgeHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")

    def send_cors_headers(self):
        for key, val in CORS_HEADERS.items():
            self.send_header(key, val)

    def send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, code, text):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_cors_headers()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    # ── OPTIONS (CORS pre-flight) ──────────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    # ── GET ───────────────────────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self.send_text(200, "SN MOBIDEER Bridge OK")
        elif path == "/master":
            self._handle_get_master()
        else:
            self.send_text(404, "Not Found")

    # ── /master ───────────────────────────────────────────────────────────
    def _handle_get_master(self):
        try:
            if not os.path.isfile(MASTER_FILE):
                self.send_text(404, "Master file not found")
                return
            with open(MASTER_FILE, "r", newline="", encoding="utf-8-sig") as f:
                content = f.read()
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_json(500, {"error": str(e)})

    # ── POST ──────────────────────────────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/print":
            self._handle_print()
        elif path == "/update-master":
            self._handle_update_master()
        else:
            self.send_text(404, "Not Found")

    # ── /print ────────────────────────────────────────────────────────────
    def _handle_print(self):
        try:
            rows = json.loads(self.read_body())

            # Write CSV for BarTender
            os.makedirs(os.path.dirname(CSV_FILENAME), exist_ok=True)
            with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    writer.writerow({fn: row.get(fn, "") for fn in FIELDNAMES})

            # Trigger BarTender — non-blocking so bridge stays online
            print(f"[BarTender] Launching with {len(rows)} rows...")
            subprocess.Popen([BARTENDER_EXE, f'/f={BTW_FILEPATH}', '/p', '/x'])

            # Auto-press Enter on BarTender "Select Records" dialog after 3 seconds (PowerShell hidden)
            ps_script = (
                'Start-Sleep -Seconds 3\r\n'
                '$ws = New-Object -ComObject WScript.Shell\r\n'
                "# Try 'Select Records' dialog first (BarTender data-source dialog)\r\n"
                "if ($ws.AppActivate('Select Records')) {\r\n"
                '    Start-Sleep -Milliseconds 500\r\n'
                "    $ws.SendKeys('~')\r\n"
                "    Start-Sleep -Seconds 2\r\n"
                '} elseif ($ws.AppActivate(\'Print\')) {\r\n'
                '    Start-Sleep -Milliseconds 500\r\n'
                "    $ws.SendKeys('~')\r\n"
                "    Start-Sleep -Seconds 2\r\n"
                '} elseif ($ws.AppActivate(\'SN Labels\')) {\r\n'
                '    Start-Sleep -Milliseconds 500\r\n'
                "    $ws.SendKeys('~')\r\n"
                '}\r\n'
            )
            import tempfile
            ps_path = os.path.join(tempfile.gettempdir(), 'bt_autoclick.ps1')
            with open(ps_path, 'w', encoding='utf-8') as psf:
                psf.write(ps_script)
            subprocess.Popen(
                ['powershell', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', ps_path],
                creationflags=0x00000008  # DETACHED_PROCESS
            )
            print("[BarTender] Auto-click PowerShell dispatched.")

            self.send_json(200, {"status": "ok", "rows": len(rows)})

        except Exception as e:
            self.send_json(500, {"error": str(e)})

    # ── /update-master ────────────────────────────────────────────────────
    def _handle_update_master(self):
        try:
            new_rows = json.loads(self.read_body())

            existing_skus = set()
            file_exists = os.path.isfile(MASTER_FILE)

            if file_exists:
                with open(MASTER_FILE, "r", newline="", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        sku_val = row.get("SKU", "")
                        if sku_val:
                            existing_skus.add(sku_val.upper())

            added = []
            to_append = []
            for row in new_rows:
                sku = row.get("SKU", "")
                if not sku:
                    continue
                if sku.upper() not in existing_skus:
                    to_append.append(row)
                    existing_skus.add(sku.upper())
                    added.append(sku)

            if to_append:
                write_header = not file_exists
                with open(MASTER_FILE, "a", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
                    if write_header:
                        writer.writeheader()
                    for row in to_append:
                        writer.writerow({fn: row.get(fn, "") for fn in FIELDNAMES})

            self.send_json(200, {
                "added": added,
                "message": f"{len(added)} new SKU(s) added to master CSV."
            })

        except Exception as e:
            self.send_json(500, {"error": str(e)})


if __name__ == "__main__":
    server = http.server.HTTPServer(("", PORT), BridgeHandler)
    print(f"SN MOBIDEER Bridge running on http://localhost:{PORT}")
    print(f"  CSV  → {CSV_FILENAME}")
    print(f"  BTW  → {BTW_FILEPATH}")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBridge stopped.")
