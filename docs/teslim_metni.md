# Teslim formu metinleri

Cerebral Valley teslim formunun alanlarını göremiyorum (sayfa giriş istiyor). Aşağıda hackathon formlarında en sık geçen alanlar için hazır metinler var. Formdaki alan adları farklıysa en yakın metni kullan. Karakter sınırı varsa kısa sürümlere geç. Tüm sayılar README ile aynı.

---

## Project name

Traffic Twin

## Tagline / one-liner (≤ 100 karakter)

One camera to a tested signal plan: SAM 3.1 builds a traffic twin, Muse Spark retimes the lights.

*Daha kısa (≤ 60):* One camera to a verified signal plan: SAM 3.1 + Muse Spark

## Track / problem statement

Build for Your World

*Gerekçe (form sorarsa):* I'm stuck at traffic lights every day. The project turns the cameras cities already have into the evidence needed to retime a signal.

## Description (uzun, ~250 kelime)

I lose time at traffic lights every day. Retiming a signal is cheap, but doing it well takes a field survey of turning counts, queues and the current plan. Most intersections already have a camera.

Traffic Twin turns one fixed-camera video into a calibrated traffic simulation and lets an agent retime the signal inside it. SAM 3.1, through the Meta Model API, detects every car in 5,610 frames of a real Los Angeles intersection (FHWA NGSIM, Lankershim Blvd). From those detections the pipeline solves the camera calibration with no hand-placed points, tracks vehicles on the ground, measures turning counts and queues, and recovers the signal plan from vehicle movements alone. It discovered the intersection's lead-lag left turn this way. A SUMO simulation is then calibrated to the video.

A Muse Spark agent (muse-spark-1.3, tool calling) reads the intersection, cites video evidence, compares against the textbook Webster plan, and tests timings in the twin. It cut average delay from 24.6 s to 22.3 s, and no approach got worse. Webster scored 32.2 s.

Every number is checked. NGSIM's hand-verified trajectories are used only for scoring, never as input. The tracks have a median position error of 0.8 m, and vehicle counts are within 2.5%. The recovered cycle matches ground truth at 101 s. A verifier re-simulates the agent's answer, checks every number it reported, and re-tests it on 10 random seeds the agent never saw: delay goes from 24.7 s to 22.6 s, with no overlap.

## Description (kısa, ~80 kelime)

Traffic Twin turns one fixed-camera video into a calibrated traffic simulation. SAM 3.1 detects every car in a real Los Angeles intersection; from that the pipeline solves the camera calibration, turning counts, queues and the signal plan, each checked against hand-verified ground truth (0.8 m median error, counts within 2.5%). A Muse Spark agent then tests signal timings in the twin. It cut average delay 9%, a gain that held on 10 random seeds the agent never saw.

## How we built it / Meta models used

- **SAM 3.1** (Meta Model API, image mode, concept prompt "car") on every 2nd frame. Video mode tracks at most 16 objects per frame, but this intersection averages 32 cars per frame and has more than 16 in 98% of frames, so tracking is done on our side in ground coordinates.
- **Muse Spark 1.3** (Responses API, tool calling) as the signal-planning agent, with four tools: intersection_summary, video_evidence, webster_baseline, test_plan. History is kept on the client with encrypted reasoning replay.
- Python, OpenCV, SciPy (Hungarian matching, homography), Eclipse SUMO + TraCI for the simulation, FastAPI and Chart.js for the demo.
- Camera calibration and the video/trajectory time offset are solved from the data. The signal plan is recovered from the autocorrelation of crossing events and from where crossings cluster within the cycle.

## Challenges we ran into

- Ground truth only covers Lankershim, so correct side-street detections pulled the first (ICP) calibration off. A grid search scored by one-sided coverage fixed it.
- Right turns first came out as zero, because turning cars cut the corner and never reach the intersection centre.
- Tuning SUMO's driver parameters barely mattered. The big errors were structural: the lead-lag phase order and the turn-bay lane counts.
- A plot in our own demo exposed a phase-alignment bug caused by the simulation warm-up. Fixing it changed our reported twin error from 3.9 to 4.2 vehicles. We report the correct number.
- Server-side response state expired mid-run in long agent loops, so history is now kept on the client.

## What's next

More intersections and time periods, live camera feeds, pedestrian detection (pedestrians are only timing constraints today), and coordinating signals along a corridor.

## Built during the hackathon (kurallar bunu istiyor)

All code was written during the hackathon (Oct 26 to Nov 4, 2026). The commit history on GitHub shows the order it was built in. The data is public (NGSIM, CC BY 2.0). No earlier code was reused.

## Links

- Repository: https://github.com/alper-tekin/trafik-ikizi
- Demo video: *(YouTube Liste dışı linkini buraya ekle)*
- Live demo: *(form sorarsa)* The demo runs locally with one command (see the README). Viewing replays the recorded agent run, so it uses no API credits.

## AI tools disclosure (form sorarsa)

Claude (Anthropic) was used as a coding assistant. The product itself runs on Meta models: SAM 3.1 for perception and Muse Spark for the agent.

---

## Teslim öncesi kontrol listesi

- [ ] Repo herkese açık: https://github.com/alper-tekin/trafik-ikizi (gizli pencerede aç ve kontrol et)
- [ ] Demo videosu YouTube'da **Liste dışı**, gizli pencerede açılıyor, 3:00'ı geçmiyor
- [ ] Videoda yalnızca hackathon sırasında yapılanlar gösteriliyor
- [ ] Formda tek kişilik takım olarak kendin varsın (Representative sensin)
- [ ] Son tarih: **4 Kasım 21:00 ET = 5 Kasım 05:00 TR**. Geç teslim kabul edilmiyor.
