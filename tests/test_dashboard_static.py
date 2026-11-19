import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "src" / "multi_star" / "static" / "dashboard.html"


class DashboardHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canvas_ids = set()
        self.external_assets = []
        self.form_ids = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "canvas" and attributes.get("id"):
            self.canvas_ids.add(attributes["id"])
        if tag == "form" and attributes.get("id"):
            self.form_ids.add(attributes["id"])
        if tag == "script" and attributes.get("src"):
            self.external_assets.append((tag, attributes["src"]))
        if tag == "link" and attributes.get("href"):
            self.external_assets.append((tag, attributes["href"]))
        if tag == "img" and attributes.get("src"):
            self.external_assets.append((tag, attributes["src"]))


class DashboardStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = DASHBOARD.read_text(encoding="utf-8")
        cls.parser = DashboardHTMLParser()
        cls.parser.feed(cls.html)

    def test_required_canvases_exist(self):
        self.assertEqual(
            {
                "satellite-canvas",
                "uv-canvas",
                "psf-canvas",
                "spectrum-canvas",
            },
            self.parser.canvas_ids,
        )

    def test_snapshot_and_command_api_paths_exist(self):
        self.assertIn("'/api/snapshot'", self.html)
        self.assertIn("'/mode'", self.html)
        self.assertIn("'/events'", self.html)
        self.assertIn("'/small-sat/fault'", self.html)
        self.assertIn("'/small-sat/recover'", self.html)
        self.assertIn("'/test/suspend'", self.html)
        self.assertIn("setInterval(fetchSnapshot, 1000)", self.html)
        self.assertRegex(self.html, r"fetch\(SNAPSHOT_PATH")
        self.assertRegex(self.html, r"postJson\(MODE_PATH")
        self.assertRegex(self.html, r"postJson\(EVENTS_PATH")
        self.assertRegex(self.html, r"FAULT_PATH\s*:\s*RECOVER_PATH")
        self.assertRegex(self.html, r"postJson\(SUSPEND_PATH,\s*\{\s*seconds:\s*22\s*\}")

    def test_no_external_script_style_or_image_dependencies(self):
        self.assertEqual([], self.parser.external_assets)
        self.assertNotRegex(
            self.html,
            re.compile(r"(?:src|href)\s*=\s*['\"]https?://", re.IGNORECASE),
        )
        self.assertNotIn("@import", self.html.lower())

    def test_required_javascript_functions_exist(self):
        functions = {
            "fetchSnapshot",
            "drawSatellitePositions",
            "drawUvCoverage",
            "drawPsf",
            "drawInputSpectrum",
            "updateMetrics",
            "renderEvents",
            "setMode",
            "submitEvent",
            "setSatelliteFault",
            "suspendMain",
            "parseCsvRows",
            "parseCsvEvents",
            "validateEvent",
            "parseEventFile",
            "loadEventFile",
            "injectFileEvents",
        }
        for function in functions:
            with self.subTest(function=function):
                self.assertRegex(self.html, rf"function\s+{function}\s*\(")

    def test_drawings_use_snapshot_or_explicit_synthetic_input(self):
        self.assertIn("snapshot.small_satellites", self.html)
        self.assertIn("snapshot.uv_points", self.html)
        self.assertIn("state.snapshot.psf", self.html)
        self.assertIn("createImageData(columns, rows)", self.html)
        self.assertIn("Math.pow(2, spectralIndex)", self.html)
        self.assertIn("SYNTHETIC INPUT · 非快照实测", self.html)
        self.assertIn("等待真实快照", self.html)

    def test_controls_and_event_fields_exist(self):
        self.assertIn("event-form", self.parser.form_ids)
        for mode in ("SURVEY", "FIXED_SOURCE", "CALIBRATION"):
            self.assertIn(f'data-mode="{mode}"', self.html)
        for field in (
            "event_id",
            "target_id",
            "frequency_hz",
            "flux_jy",
            "confidence",
            "spectral_index",
            "expiry_s",
        ):
            self.assertIn(f'name="{field}"', self.html)

    def test_fault_controls_and_satellite_options_exist(self):
        for element_id in (
            "fault-satellite",
            "fault-inject",
            "fault-recover",
            "fault-status",
            "main-suspend",
            "main-status",
        ):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', self.html)
        for index in range(9):
            self.assertIn(f'<option value="small-sat-{index}">', self.html)
        self.assertIn("{ satellite_id: satelliteId }", self.html)
        self.assertIn("暂停当前主控 22 秒（测试切换）", self.html)
        self.assertNotIn("window.confirm(", self.html)
        self.assertIn("function requireSecondClick", self.html)
        self.assertIn("再次点击确认", self.html)

    def test_event_file_controls_sample_and_limits_exist(self):
        for element_id in (
            "event-file",
            "file-load",
            "file-inject",
            "file-preview",
            "file-status",
        ):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', self.html)
        self.assertIn('type="file" accept=".csv,.json"', self.html)
        self.assertIn('href="/sample-events.csv"', self.html)
        self.assertIn("MAX_FILE_BYTES = 1024 * 1024", self.html)
        self.assertIn("MAX_FILE_EVENTS = 100", self.html)
        self.assertIn("await file.text()", self.html)
        self.assertIn("file.size > MAX_FILE_BYTES", self.html)
        self.assertIn("records.length > MAX_FILE_EVENTS", self.html)

    def test_file_parser_and_injection_use_validation_and_real_receipts(self):
        self.assertIn("event_id,target_id,frequency_hz,flux_jy,confidence,spectral_index,expiry_s", self.html)
        self.assertIn("inQuotes", self.html)
        self.assertNotIn(".split(',')", self.html)
        self.assertIn("Array.isArray(parsed.events)", self.html)
        self.assertRegex(
            self.html,
            re.compile(
                r"for \(const event of events\).*?await postJson\(EVENTS_PATH, event\)",
                re.DOTALL,
            ),
        )
        self.assertIn("body.duplicate === true", self.html)
        self.assertIn("body.accepted === true", self.html)
        self.assertIn("accepted=${accepted}", self.html)
        self.assertIn("duplicate=${duplicate}", self.html)
        self.assertIn("failed=${failed}", self.html)

    def test_usage_guide_describes_modes_and_file_scope(self):
        self.assertIn("<details", self.html)
        self.assertIn("使用说明", self.html)
        self.assertIn("不是 FITS 高保真天空输入", self.html)
        for mode in ("SURVEY", "FIXED_SOURCE", "CALIBRATION"):
            self.assertIn(mode, self.html)

    def test_operation_status_never_dumps_raw_json(self):
        self.assertNotIn("JSON.stringify(body)", self.html)
        self.assertIn("function responseSummary", self.html)
        self.assertIn("任务数", self.html)
        self.assertIn("suspended_seconds", self.html)


if __name__ == "__main__":
    unittest.main()
