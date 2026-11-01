"""Muse Spark sinyal planlama ajanı.

Ajan kendi başına sayı uydurmaz: kavşağı, videodan ölçülen kuyrukları ve
her plan önerisinin simülasyon sonucunu araçlardan alır. Son cevaptaki her
iddia bir araç çıktısına dayanmak zorundadır; bu yüzden her adım kaydedilir
(arayüz ve doğrulama için).
"""

import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from trafik import olcum
from trafik.akis import talep_sayimlari
from trafik.degerlendir import KISIT, SURE_S, degerlendir, webster
from trafik.sumo_ag import plan_videodan

MODEL = "muse-spark-1.3"
YON_ADI = {1: "eastbound", 2: "northbound", 3: "westbound", 4: "southbound"}
KOL_EN = {"K": "from north (southbound)", "G": "from south (northbound)", "D": "from east", "B": "from west"}
HAREKET_ADI = {1: "through", 2: "left", 3: "right"}

TALIMAT = f"""You are a traffic signal engineer working on a calibrated digital twin of one real
intersection: Lankershim Blvd and Universal Hollywood Dr, Los Angeles. The twin was built from
fixed-camera video: SAM 3.1 detected the vehicles, tracks gave turning counts and the current
signal plan, and a SUMO simulation was calibrated to the queues seen in the video. The twin
replays the vehicles from the video: each one enters at the second, place, lane and speed it
was first seen, and goes where it went (buses and trucks included). A plan you test is applied
to exactly that traffic.

Your job: find a signal plan that reduces average vehicle delay, and explain it with evidence.

Rules:
- Never invent numbers. Every number you state must come from a tool result in this conversation.
- Start with intersection_summary. Look at video_evidence for the worst approach before proposing.
- Test every plan you recommend with test_plan. Try at least 4 different plans, including the
  Webster baseline. Change one idea at a time so you can explain what each change did.
- Respect the constraints: cross-street green >= {KISIT['ara_sokak_min_s']} s (pedestrians cross
  Lankershim then), shared Lankershim green >= {KISIT['ortak_min_s']} s, cycle
  {KISIT['dongu_min_s']}-{KISIT['dongu_max_s']} s.
- Do not trade a small average gain for a large loss on one approach: report per-approach delay.
- Results are from a simulation calibrated to 18 minutes of morning traffic in 2005. Say so.
- Seeds change driver behaviour only (the traffic is the real one). Seed-to-seed spread is
  reported for each test; treat differences smaller than that spread as noise.

When you are done, reply with a single JSON object and nothing else:
{{"recommended_plan": {{"sol_onde": s, "guney_onde": s, "ortak": s, "ara_sokak": s}},
  "baseline_avg_delay_s": n, "recommended_avg_delay_s": n,
  "summary": "2-3 sentences for a city traffic engineer",
  "evidence": [{{"claim": "...", "source": "tool name", "value": "..."}}],
  "caveats": ["..."]}}"""

ARACLAR = [
    {
        "type": "function",
        "name": "intersection_summary",
        "description": "Demand per movement (veh/h) measured from video, the current signal plan recovered "
                       "from the video, its simulated delays, calibration quality and constraints.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "test_plan",
        "description": "Simulate a signal plan in the calibrated twin on the real traffic from the video "
                       "(3 seeds of driver behaviour) and return average, "
                       "p95, per-approach and per-movement delay. Phase order is fixed: "
                       "1) sol_onde: southbound left only; 2) guney_onde: southbound through+left, "
                       "northbound red; 3) ortak: both Lankershim directions through, lefts permissive; "
                       "4) ara_sokak: cross street. 3 s yellow + 1 s all-red after phases 3 and 4. "
                       "Set sol_onde or guney_onde to 0 to remove that phase.",
        "parameters": {
            "type": "object",
            "properties": {
                "sol_onde": {"type": "number", "description": "southbound protected left only, seconds"},
                "guney_onde": {"type": "number", "description": "southbound through + left lead, seconds"},
                "ortak": {"type": "number", "description": "both Lankershim directions through, seconds"},
                "ara_sokak": {"type": "number", "description": "cross street green, seconds"},
            },
            "required": ["sol_onde", "guney_onde", "ortak", "ara_sokak"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "webster_baseline",
        "description": "Classic Webster formula plan from measured flow ratios (with pedestrian minimums), "
                       "and its simulated delays. A textbook baseline to compare against.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "video_evidence",
        "description": "Queue evidence from the real video for one approach: average queue across the "
                       "signal cycle, and the 3 worst moments (video timestamps) to show as clips.",
        "parameters": {
            "type": "object",
            "properties": {
                "approach": {"type": "string", "enum": ["K", "G", "D", "B"],
                             "description": "K: from north, G: from south, D: from east, B: from west"},
            },
            "required": ["approach"],
            "additionalProperties": False,
        },
    },
]


class Ortam:
    """Ajanın araçlarının dayandığı veri ve önbellek."""

    def __init__(self):
        akis = pd.read_parquet("data/akis_izler.parquet")
        self.sayim = talep_sayimlari(akis)
        kal = json.load(open("data/sim_kalibrasyon.json", encoding="utf-8"))
        self.kalibrasyon = kal
        self.surucu = {"tau": kal["en_iyi"]["tau"], "accel": kal["en_iyi"]["accel"]}
        y, C = plan_videodan()
        self.mevcut = {"sol_onde": y["sol_onde"], "guney_onde": y["guney_onde"], "ortak": y["ortak"],
                       "ara_sokak": C - y["sol_onde"] - y["guney_onde"] - y["ortak"] - 8}
        plan = json.load(open("data/sinyal_plani.json", encoding="utf-8"))
        self.dongu, self.faz0 = plan["dongu_s"], plan["faz0_video_s"]
        self.video = olcum.noktalar_izden(pd.read_parquet("data/izler_kamera2.parquet"), akis)
        self._onbellek: dict = {}

    def dene(self, plan: dict) -> dict:
        anahtar = json.dumps({k: round(float(plan[k]), 1) for k in sorted(plan)})
        if anahtar not in self._onbellek:
            self._onbellek[anahtar] = degerlendir({k: float(v) for k, v in plan.items()}, self.sayim, self.surucu)
        return self._onbellek[anahtar]

    # --- araçlar ---
    def intersection_summary(self) -> dict:
        talep, buyuk = {}, {}
        for anahtar, n in sorted(self.sayim.items(), key=lambda x: tuple(map(str, x[0]))):
            ad = f"{YON_ADI[anahtar[0]]} {HAREKET_ADI[anahtar[1]]}"
            talep[ad] = talep.get(ad, 0) + round(n / SURE_S * 3600)
            if len(anahtar) > 2:
                buyuk[ad] = round(n / SURE_S * 3600)
        k = self.kalibrasyon
        return {
            "demand_veh_per_h": talep,
            "of_which_buses_trucks_veh_per_h": buyuk,
            "current_plan_from_video": {**self.mevcut, "cycle_s": self.dongu},
            "current_plan_simulated": self.dene(self.mevcut),
            "calibration": {
                "queue_profile_rmse_vs_video_veh": round(k["en_iyi"]["rmse_video"], 2),
                "queue_profile_rmse_vs_independent_ground_truth_veh": round(k["en_iyi"]["rmse_ngsim"], 2),
                "measurement_floor_video_vs_ground_truth_veh": round(k["video_vs_ngsim_rmse"], 2),
                "mean_queue_video_veh": k["video_ort_kuyruk"],
                "mean_queue_ground_truth_veh": k["ngsim_ort_kuyruk"],
            },
            "constraints": KISIT,
            "approach_codes": KOL_EN,
        }

    def test_plan(self, sol_onde, guney_onde, ortak, ara_sokak) -> dict:
        return self.dene({"sol_onde": sol_onde, "guney_onde": guney_onde, "ortak": ortak, "ara_sokak": ara_sokak})

    def webster_baseline(self) -> dict:
        w = webster(self.sayim)
        return {**w, "simulated": self.dene(w["plan"])}

    def video_evidence(self, approach: str) -> dict:
        d = self.video[self.video.giris == approach]
        q = d[olcum.yaklasimda(d) & (d.hiz < olcum.DURGUN_MS)]
        seri = q.groupby(np.round(q.t)).arac.nunique()
        profil = olcum.kuyruk_profili(self.video, self.dongu, self.faz0).get(approach)
        en_kotu, secilen = [], []
        for t, n in seri.sort_values(ascending=False).items():
            if all(abs(t - s) > 60 for s in secilen):
                secilen.append(t)
                en_kotu.append({"video_time_s": float(t), "stopped_vehicles": int(n)})
            if len(secilen) == 3:
                break
        return {
            "approach": KOL_EN[approach],
            "mean_stopped_vehicles": round(float(seri.reindex(np.arange(0, 1122), fill_value=0).mean()), 1),
            "worst_moments": en_kotu,
            "queue_by_cycle_second_every_10s": [round(float(v), 1) for v in profil.iloc[::10]] if profil is not None else [],
            "cycle_second_0_is": "start of southbound through green in the current plan "
                                 "(southbound-only left runs in the ~15 s before it)",
        }


def calistir(soru: str = "Find a better signal plan for this intersection.", en_cok_adim: int = 20,
             kayit_klasoru: str = "data/ajan", bildir=None) -> dict:
    """bildir(olay: dict) verilirse her araç çağrısında ve sonda çağrılır (arayüz akışı için)."""
    bildir = bildir or (lambda olay: None)
    load_dotenv()
    client = OpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])
    ortam = Ortam()
    kayit = {"soru": soru, "model": MODEL, "adimlar": [], "baslangic": time.time()}

    # Sunucudaki yanıt kaydı uzun ajan döngülerinde süresi dolup kaybolabiliyor
    # ("referenced response not found"); geçmiş bizde tutulur ve her istekte
    # şifreli akıl yürütme içeriğiyle birlikte yeniden gönderilir.
    gecmis: list = [{"role": "user", "content": soru}]

    def sor():
        return client.responses.create(model=MODEL, instructions=TALIMAT, input=gecmis, tools=ARACLAR,
                                       store=False, include=["reasoning.encrypted_content"])

    yanit = sor()
    for _ in range(en_cok_adim):
        cagrilar = [o for o in yanit.output if o.type == "function_call"]
        if not cagrilar:
            break
        gecmis += [o.model_dump(exclude_none=True) for o in yanit.output]
        cikti = []
        for c in cagrilar:
            arg = json.loads(c.arguments or "{}")
            try:
                sonuc = getattr(ortam, c.name)(**arg)
            except Exception as hata:  # ajan hatayı görsün ve düzeltsin
                sonuc = {"error": repr(hata)}
            kayit["adimlar"].append({"arac": c.name, "argumanlar": arg, "sonuc": sonuc})
            bildir({"tur": "adim", "no": len(kayit["adimlar"]), **kayit["adimlar"][-1]})
            print(f"[{len(kayit['adimlar'])}] {c.name} {arg} -> "
                  f"{sonuc.get('ort_gecikme_s', sonuc.get('simulated', {}).get('ort_gecikme_s', '')) if isinstance(sonuc, dict) else ''}",
                  flush=True)
            cikti.append({"type": "function_call_output", "call_id": c.call_id,
                          "output": json.dumps(sonuc, ensure_ascii=False)})
        gecmis += cikti
        yanit = sor()

    if any(o.type == "function_call" for o in yanit.output) or not yanit.output_text.strip():
        # Adım bütçesi bitti: yeni araç çağrısı yaptırmadan elindekilerle son cevabı iste.
        gecmis.append({"role": "user", "content": "Testing budget is used up. Do not call more tools. "
                                                  "Reply now with the final JSON, using only results above."})
        yanit = client.responses.create(model=MODEL, instructions=TALIMAT, input=gecmis, tools=ARACLAR,
                                        tool_choice="none", store=False)

    metin = yanit.output_text
    kayit["cevap_metni"] = metin
    try:
        kayit["cevap"] = json.loads(metin[metin.index("{"): metin.rindex("}") + 1])
    except ValueError:
        kayit["cevap"] = None
    kayit["bitis"] = time.time()
    bildir({"tur": "cevap", "cevap": kayit["cevap"], "cevap_metni": metin})
    kayit["dogrulama"] = dogrula(kayit, ortam)
    bildir({"tur": "dogrulama", "dogrulama": kayit["dogrulama"]})

    Path(kayit_klasoru).mkdir(parents=True, exist_ok=True)
    yol = Path(kayit_klasoru) / f"kosu_{int(kayit['baslangic'])}.json"
    yol.write_text(json.dumps(kayit, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    kayit["yol"] = str(yol)
    return kayit


def dogrula(kayit: dict, ortam: Ortam) -> dict:
    """Ajanın son cevabını araç çıktılarına karşı denetler: önerilen plan
    gerçekten test edildi mi, bildirilen gecikmeler simülasyonla aynı mı."""
    c = kayit.get("cevap")
    if not c:
        return {"gecerli_json": False}
    plan = c.get("recommended_plan", {})
    test = [a for a in kayit["adimlar"] if a["arac"] == "test_plan"]
    denendi = any(all(abs(float(a["argumanlar"].get(k, -1)) - float(plan.get(k, -2))) < 0.51 for k in plan)
                  for a in test) if plan else False
    plan = {k: float(plan[k]) for k in ("sol_onde", "guney_onde", "ortak", "ara_sokak")} if plan else {}
    gercek = ortam.dene(plan) if plan else {}
    taban = ortam.dene(ortam.mevcut)
    sonuc = {
        "gecerli_json": True,
        "onerilen_plan_test_edildi": denendi,
        "onerilen_gecikme_bildirilen": c.get("recommended_avg_delay_s"),
        "onerilen_gecikme_simulasyon": gercek.get("ort_gecikme_s"),
        "taban_gecikme_bildirilen": c.get("baseline_avg_delay_s"),
        "taban_gecikme_simulasyon": taban.get("ort_gecikme_s"),
        "plan_kisitlara_uygun": gercek.get("gecerli", False),
    }
    if gercek.get("gecerli"):
        # Ajanın "hiçbir yön kötüleşmedi" gibi iddialarını denetlemek için yön bazlı fark.
        sonuc["kol_gecikme_farki_s"] = {
            k: round(gercek["kol_gecikme_s"][k] - v, 1) for k, v in taban["kol_gecikme_s"].items()
        }
    if gercek.get("gecerli"):
        # Ajan planı videodaki trafikle (gerçek gelişler, tohum 1-3) seçti; hiç görmediği
        # rastgele trafikte de (sayımlardan, tohum 11-20) kazanç sürüyor mu? Tek bir sabaha
        # ezber kontrolü.
        tohumlar = tuple(range(11, 21))
        yeni = degerlendir(plan, ortam.sayim, ortam.surucu, tohumlar, gelis="rastgele")
        eski = degerlendir(ortam.mevcut, ortam.sayim, ortam.surucu, tohumlar, gelis="rastgele")
        sonuc["bagimsiz_10_tohum"] = {
            "taban_ort_gecikme_s": eski["ort_gecikme_s"],
            "onerilen_ort_gecikme_s": yeni["ort_gecikme_s"],
            "taban_tohum_araligi_s": eski["ort_gecikme_tohum_araligi_s"],
            "onerilen_tohum_araligi_s": yeni["ort_gecikme_tohum_araligi_s"],
        }
    return sonuc
