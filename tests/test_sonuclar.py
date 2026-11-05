import json
from pathlib import Path
import tempfile
import unittest

from trafik.sonuclar import ozetle, trip_oku


class TripAccounting(unittest.TestCase):
    def read(self, vehicles, trips):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "routes.xml").write_text(f"<routes>{vehicles}</routes>")
            (root / "trips.xml").write_text(f"<tripinfos>{trips}</tripinfos>")
            return trip_oku(root / "trips.xml", root / "routes.xml").assign(tohum=1)

    def test_delayed_warmup_vehicle_does_not_enter_evaluation(self):
        rows = self.read('<vehicle id="Ks.1" depart="119"/><vehicle id="Ks.2" depart="120"/>',
                         '<tripinfo id="Ks.1" depart="140" departDelay="21" arrival="160" timeLoss="10" waitingTime="4"/>'
                         '<tripinfo id="Ks.2" depart="125" departDelay="5" arrival="145" timeLoss="10" waitingTime="4"/>')
        result = ozetle(rows, (1,))
        self.assertEqual(result["tamamlanan_arac"], 1)
        self.assertEqual(result["ort_toplam_kayip_s"], 15)
        self.assertEqual(result["arac_basi_durma_bekleme_s"], 4)
        self.assertTrue(result["tam_karsilastirma"])

    def test_unfinished_uninserted_and_missing_cannot_disappear(self):
        vehicles = ''.join(f'<vehicle id="Ks.{i}" depart="120"/>' for i in range(1, 5))
        rows = self.read(vehicles,
                         '<tripinfo id="Ks.1" depart="120" departDelay="0" arrival="130" timeLoss="2" waitingTime="1"/>'
                         '<tripinfo id="Ks.2" depart="125" departDelay="5" arrival="-1" timeLoss="999" waitingTime="999"/>'
                         '<tripinfo id="Ks.3" depart="-1" departDelay="100" arrival="-1" timeLoss="-1" waitingTime="-1"/>')
        result = ozetle(rows, (1,))
        count = result["tohum_talep_durumu"]["1"]
        self.assertEqual(count["planlanan"], 4)
        self.assertEqual(count["tamamlanan"], 1)
        self.assertEqual(count["agda_tamamlanmayan"], 1)
        self.assertEqual(count["girememis"], 1)
        self.assertEqual(count["kaydi_eksik"], 1)
        self.assertEqual(result["ort_gecikme_s"], 2)
        self.assertFalse(result["tam_karsilastirma"])

    def test_no_completions_returns_null_metrics_not_nan(self):
        rows = self.read('<vehicle id="Ks.1" depart="120"/>', '')
        result = ozetle(rows, (1,))
        self.assertIsNone(result["ort_gecikme_s"])
        self.assertIsNone(result["p95_bekleme_s"])
        self.assertFalse(result["tam_karsilastirma"])
        json.dumps(result, allow_nan=False)

    def test_unknown_flow_cohort_blocks_complete_comparison(self):
        rows = self.read('<flow id="Ks" begin="0" end="1122" vehsPerHour="100"/>',
                         '<tripinfo id="Ks.0" depart="-1" departDelay="100" arrival="-1" timeLoss="-1" waitingTime="-1"/>')
        result = ozetle(rows, (1,))
        self.assertEqual(result["tohum_talep_durumu"]["1"]["kohortu_belirsiz"], 1)
        self.assertFalse(result["tam_karsilastirma"])

    def test_duplicate_records_are_rejected(self):
        trip = '<tripinfo id="Ks.1" depart="120" departDelay="0" arrival="130" timeLoss="2" waitingTime="1"/>'
        with self.assertRaises(ValueError):
            self.read('<vehicle id="Ks.1" depart="120"/>', trip + trip)

    def test_empty_seed_is_not_a_complete_comparison(self):
        rows = self.read('<vehicle id="Ks.1" depart="120"/>', '')
        self.assertFalse(ozetle(rows, (1, 2))["tam_karsilastirma"])
        with self.assertRaises(ValueError):
            ozetle(rows, (1, 1))

    def test_approach_tail_wait_is_not_hidden_by_other_approaches(self):
        rows = self.read('<vehicle id="Ks.1" depart="120"/><vehicle id="Ks.2" depart="120"/>'
                         '<vehicle id="Bs.1" depart="120"/>',
                         '<tripinfo id="Ks.1" depart="120" departDelay="0" arrival="130" timeLoss="2" waitingTime="0"/>'
                         '<tripinfo id="Ks.2" depart="120" departDelay="0" arrival="230" timeLoss="100" waitingTime="100"/>'
                         '<tripinfo id="Bs.1" depart="120" departDelay="0" arrival="130" timeLoss="2" waitingTime="1"/>')
        result = ozetle(rows, (1,))
        self.assertEqual(result["kol_p95_bekleme_s"]["from north (southbound)"], 95)
        self.assertEqual(result["kol_p95_bekleme_s"]["from west"], 1)


if __name__ == "__main__":
    unittest.main()
