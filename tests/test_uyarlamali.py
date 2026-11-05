import unittest

from trafik import uyarlamali as adaptive


class AdaptiveParameters(unittest.TestCase):
    def test_default_and_registered_maximums(self):
        self.assertEqual(adaptive.parametreleri_dogrula(), {"max_green_s": 60.0})
        for maximum in (30, 45, 60):
            self.assertEqual(adaptive.parametreleri_dogrula({"max_green_s": maximum}),
                             {"max_green_s": float(maximum)})

    def test_minimum_and_pedestrian_timings_cannot_be_overridden(self):
        for params in ({"max_green_s": 29}, {"max_green_s": float("nan")},
                       {"max_green_s": float("inf")}, {"max_green_s": True},
                       {"yellow_s": 0}, {"pedestrian_interval_s": 0}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                adaptive.parametreleri_dogrula(params)

    def test_pedestrian_priority_beats_score_and_maximum(self):
        self.assertEqual(adaptive.faz_sec("guney", 40, {"guney": 100, "ortak": 90, "ara": 0},
                                         True, ["ara"], 30),
                         ("ara", "pedestrian_service_due"))

    def test_maximum_and_demand_cleared_reasons(self):
        scores = {"guney": 10, "ortak": 90, "ara": 1}
        self.assertEqual(adaptive.faz_sec("guney", 29, scores, True, [], 30), (None, None))
        self.assertEqual(adaptive.faz_sec("guney", 30, scores, True, [], 30), ("ortak", "maximum_green"))
        self.assertEqual(adaptive.faz_sec("guney", 10, scores, False, [], 30), ("ortak", "demand_cleared"))
        self.assertEqual(adaptive.faz_sec("guney", 90, {"guney": 10, "ortak": 0, "ara": 0},
                                         True, [], 30), (None, None))

    def test_audit_requires_whole_green_and_keeps_observation_boundaries(self):
        audit = adaptive.YayaKaydi()
        audit.baslat("ara", 5)
        audit.guncelle(34.5)
        audit.bitir(34.5)
        audit.baslat("ara", 50)
        audit.guncelle(80)
        audit.guncelle(85)
        result = audit.ozet(100)
        self.assertIsNone(result["hizmetler"][0]["tamamlanma_s"])
        self.assertEqual(result["hizmetler"][1]["tamamlanma_s"], 80)
        self.assertEqual(result["tamamlanmayan_hizmet_sayisi"], 1)
        self.assertEqual(result["azami_tamamlanma_boslugu_s"]["ara"], 80)
        self.assertEqual(result["azami_hizmetsiz_bosluk_s"]["ara"], 80)
        self.assertEqual(result["azami_hizmetsiz_bosluk_s"]["ortak"], 100)
        self.assertEqual(sum(e["olay"] == "pedestrian_service_complete" for e in result["olaylar"]), 1)
        self.assertFalse(result["azami_aralik_garantisi"])

    def test_continuous_green_remains_service_after_first_completion(self):
        audit = adaptive.YayaKaydi()
        audit.baslat("ortak", 0)
        audit.guncelle(18)
        result = audit.ozet(200)
        self.assertEqual(result["azami_tamamlanma_boslugu_s"]["ortak"], 182)
        self.assertEqual(result["azami_hizmetsiz_bosluk_s"]["ortak"], 18)


if __name__ == "__main__":
    unittest.main()
