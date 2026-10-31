# Demo videosu senaryosu (3:00)

Anlatım İngilizce (jüri uluslararası), yönergeler Türkçe. Toplam anlatım 402 kelime. Dakikada ~150 kelimelik sakin bir hızla yaklaşık 2:41 sürüyor, geri kalanı sessiz geçişlere kalıyor.

Kural hatırlatması: demo yalnızca hackathon sırasında yapılanları göstermeli. Burada gösterilen her şey (pipeline, kalibrasyon, takip, sinyal çıkarımı, SUMO ikizi, ajan, doğrulayıcı, arayüz) 26 Ekim'den sonra yazıldı. 2:45'teki kapanış cümlesi bunu açıkça söylüyor.

## Hazırlık

- Sunucuyu başlat: `.venv/Scripts/python -m uvicorn web.app:app --port 8020`, sonra tarayıcıda `http://localhost:8020` adresini aç.
- Tarayıcıyı tam ekran yap (F11), yakınlaştırmayı %110 civarına ayarla. 1920x1080 kayıt al.
- Kayıt aracı: Windows'ta Win+Alt+R (Xbox Game Bar) ya da OBS. Mikrofonu ayrı kaydedip sonra senkronlamak daha temiz ses verir.
- Kayıttan önce sayfayı bir kez baştan sona kaydır. Video ve veriler önbelleğe girer, kayıt sırasında takılma olmaz.
- Videoyu 60. saniyeye getirip duraklat. 66. saniyede kuzeyden gelen yönde 26 araçlık en uzun kuyruk var.
- "Replay the recorded agent run" düğmesine kayıttan önce basma. Ajanın adım adım akması videonun en etkileyici anı.

---

## 0:00 – 0:15 · Açılış

**Ekran:** Sayfanın en üstü: başlık ve 5 KPI kartı.

> I spend a lot of my life stuck at traffic lights. Retiming a signal is cheap, but knowing *how* to retime it takes a field survey. Most intersections already have a camera. So I asked: can one camera and Meta's models give a city engineer a tested signal plan?

## 0:15 – 0:45 · 1 · See

**Ekran:** 1. bölüme kaydır. Videoyu 60 s'den oynat, kuşbakışı panel yanında aksın. 5-6 saniye izlet.

> This is real footage of Lankershim Boulevard in Los Angeles, from the public NGSIM dataset. SAM 3.1, through the Meta Model API, finds every car in 5,600 frames. I track them across frames and project them onto the ground, on the right. The camera calibration is solved from the data itself, with no hand-placed points. The median position error is 0.8 metres against ground truth.

**Fare:** Konum hatasından bahsederken üstteki "0.8 m" kartını göster.

## 0:45 – 1:25 · 2 · Measure

**Ekran:** 2. bölüm. Önce sayım tablosu, sonra sinyal grafiği, sonra kuyruk grafikleri.

> NGSIM also has hand-verified trajectories. I use them only to check results, never as input.
>
> Turning counts from the tracks: 1,120 vehicles against 1,149, main movements within 4 percent.

**Fare:** Sinyal grafiğine geç.

> I had no signal logs, so I recovered the signal plan from how vehicles move. The cycle is 101 seconds, matching ground truth, and the Lankershim greens are within one second. It also revealed a lead-lag plan: southbound left turns go first.

**Fare:** Kuyruk grafiklerine geç.

> Then a SUMO simulation is calibrated to the video alone. Its queues follow ground truth through most of the cycle.

## 1:25 – 2:25 · 3 · Decide

**Ekran:** 3. bölüm. "Replay the recorded agent run" düğmesine bas. Adımlar akarken konuş.

> Muse Spark gets four tools: an intersection summary, video evidence, a textbook Webster plan, and a simulator that tests any plan over three seeds. It can only state numbers that come from those tools.
>
> The Webster plan is 30 percent *worse*, 32 seconds of delay, because it has no slot for that lead-lag left. Then the agent changes one thing at a time and keeps what helps.

**Fare:** Bir video_evidence satırındaki zaman damgasına tıkla. Video o ana atlar. Sonra geri kaydır.

> Every claim links to evidence, like this queue in the real video.

**Ekran:** Recommendation kartı ve altındaki Verifier.

> Its recommendation: shorten the southbound-only lead and give the time to the shared green. Average delay drops from 24.6 to 22.3 seconds, and no approach gets worse.
>
> I don't trust the agent's word. A verifier re-runs the plan, checks every number it reported, and tests it on ten random seeds the agent never saw. The gain holds: 24.7 to 22.6 seconds, with no overlap.

## 2:25 – 2:45 · 4 · Compare

**Ekran:** 4. bölüm. Play'e bas, iki simülasyon yan yana aksın. "vehicle-minutes stopped" sayaçlarını göster.

> Both plans side by side in the twin, same traffic, same seed. Red dots are stopped cars; watch the stopped-time counters.

## 2:45 – 3:00 · Kapanış

**Ekran:** Sayfanın altı (footer) ya da GitHub reposu.

> Everything you saw was built during this hackathon. It's one intersection and one morning in 2005: a simulation, not a field trial. One camera, SAM 3.1 and Muse Spark, with every claim checked.

---

## Yedek kısaltmalar (süre aşarsa)

- 1:25 sonrasındaki "Then the agent changes one thing at a time…" cümlesini çıkar (−4 s).
- 4. bölümü 10 saniyeye indir, sadece Play'e bas ve tek cümle söyle (−8 s).

## Yükleme

- YouTube'a **Liste dışı (Unlisted)** olarak yükle. Gizli (Private) yüklersen jüri açamaz.
- Başlık önerisi: "Traffic Twin: one camera to a tested signal plan (SAM 3.1 + Muse Spark)"
- Linki gizli pencerede açıp çalıştığını kontrol et. Teslim kontrol listesinde bu var.
