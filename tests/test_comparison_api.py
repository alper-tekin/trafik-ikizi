import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from web import app as web_app


class ComparisonProvenance(unittest.TestCase):
    def test_current_report_is_served_and_stale_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "web").mkdir()
            (root / "reports").mkdir()
            (root / "input.json").write_text("original")
            digest = hashlib.sha256(b"original").hexdigest()
            (root / "reports/sprint-accounting.json").write_text(json.dumps({
                "input_hashes": {"input.json": digest}, "seeds": [1, 2, 3], "results": {}}))
            with patch.object(web_app, "KOK", root / "web"), TestClient(web_app.app) as client:
                response = client.get("/api/karsilastirma")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["seeds"], [1, 2, 3])
                (root / "input.json").write_text("changed")
                self.assertEqual(client.get("/api/karsilastirma").status_code, 409)

    def test_missing_report_returns_404(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "web").mkdir()
            with patch.object(web_app, "KOK", root / "web"), TestClient(web_app.app) as client:
                self.assertEqual(client.get("/api/karsilastirma").status_code, 404)


if __name__ == "__main__":
    unittest.main()
