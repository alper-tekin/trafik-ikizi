from pathlib import Path
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.arayuz_verisi import KARSILASTIRMA_ALANLARI, karar_penceresi, plan_ozeti, son_ajan_kosusu


class UIDataEvaluation(unittest.TestCase):
    def test_one_simulation_evaluation_produces_all_summary_fields(self):
        output = {key: i for i, key in enumerate(KARSILASTIRMA_ALANLARI)}
        with patch("trafik.degerlendir.degerlendir", return_value=output) as evaluate:
            result = plan_ozeti({"test": 1}, {}, {}, (1, 2, 3), gelis="rastgele")
        evaluate.assert_called_once_with({"test": 1}, {}, {}, (1, 2, 3), gelis="rastgele")
        self.assertEqual(result, output)

    def test_incomplete_latest_run_cannot_silently_reuse_an_old_recommendation(self):
        with tempfile.TemporaryDirectory() as folder:
            old=Path(folder)/"kosu_100.json"
            latest=Path(folder)/"kosu_200.json"
            old.write_text(json.dumps({"cevap":{"old":True}}))
            latest.write_text(json.dumps({"cevap":None,"durum":"api_hatasi"}))
            with patch("scripts.arayuz_verisi.Path.glob", return_value=[old,latest]):
                with self.assertRaises(ValueError):
                    son_ajan_kosusu()
                latest.write_text(json.dumps({"cevap":{"recommended_plan":{}}, "durum":"dogrulama_hatasi"}))
                with self.assertRaises(ValueError):
                    son_ajan_kosusu()

    def test_adaptive_decision_window_keeps_carry_in_and_ignores_completion_event(self):
        def transition(t):
            return {"olay":"transition_requested", "t":t, "onceki_faz":"ortak", "sonraki_faz":"ara",
                    "neden":"pedestrian_service_due", "gecen_yesil_s":30.0}
        events = [transition(400), transition(419.5), {"olay":"green_start", "t":423.5},
                  transition(450), transition(720)]
        self.assertEqual([x["t"] for x in karar_penceresi(events, 420, 720)], [-0.5, 30])


if __name__ == "__main__":
    unittest.main()
