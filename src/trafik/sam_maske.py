"""SAM 3.1 'one_bit' maske çözücüsü (Meta'nın @meta-sam/parser mask-codec.js'inin Python karşılığı).

Maske yükü: özel bir base85 alfabesiyle paketlenmiş baytlar; içerik, her pikseli
12 komşu pikselin bağlamıyla tahmin eden uyarlamalı bir aralık kodlayıcıdır.
Maske kendi kutusunu (x1, y1, x2, y2) kaplar: H = y2 - y1 + 1, W = x2 - x1 + 1.
"""

import re

import numpy as np

_DISLANAN = set('"\\,;<>|')
ALFABE = "".join(chr(c) for c in range(0x21, 0x7F) if chr(c) not in _DISLANAN)
_DEGER = {ch: i for i, ch in enumerate(ALFABE)}
RADIX, ONEK = 85, 5
M32 = 0xFFFFFFFF
TOP, BOTTOM = 1 << 24, 1 << 16
ARTIS, SAYI_SINIRI, BAGLAM, DOLGU = 14, 4096, 1 << 12, 2

KAYIT = re.compile(
    r"(\d+)<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)(?:;c=([\d.]+))?\|>"
    r"<\|mask;x=0;y=0(?:;c=[\d.]+)?;data=(\d+),(\d+),(.*?)\|>"
)


def _ac(yuk: str) -> bytes:
    uzunluk = 0
    for ch in yuk[:ONEK]:
        uzunluk = uzunluk * RADIX + _DEGER[ch]
    kalan = uzunluk % 4
    cikti = bytearray()
    kaynak = ONEK
    for _ in range(uzunluk // 4):
        v = 0
        for ch in yuk[kaynak:kaynak + 5]:
            v = v * RADIX + _DEGER[ch]
        kaynak += 5
        cikti += v.to_bytes(4, "big")
    if kalan:
        v = 0
        for i in range(5):
            v = v * RADIX + (_DEGER[yuk[kaynak + i]] if i < kalan + 1 else RADIX - 1)
        cikti += v.to_bytes(4, "big")[:kalan]
    return bytes(cikti)


class _AralikCozucu:
    def __init__(self, girdi: bytes):
        self.g, self.p = girdi, 0
        self.low, self.range, self.code, self.scaled = 0, M32, 0, 0
        for _ in range(4):
            self.code = ((self.code << 8) | self._oku()) & M32

    def _oku(self) -> int:
        b = self.g[self.p]
        self.p += 1
        return b

    def frekans(self, toplam: int) -> int:
        self.scaled = self.range // toplam
        v = ((self.code - self.low) & M32) // self.scaled
        return toplam - 1 if v >= toplam else v

    def coz(self, kumulatif: int, frekans: int) -> None:
        self.low = (self.low + self.scaled * kumulatif) & M32
        self.range = self.scaled * frekans
        while True:
            if (self.low ^ ((self.low + self.range) & M32)) & M32 < TOP:
                pass
            elif self.range < BOTTOM:
                self.range = (-self.low & M32) & (BOTTOM - 1)
            else:
                break
            self.code = ((self.code << 8) | self._oku()) & M32
            self.low = (self.low << 8) & M32
            self.range = (self.range << 8) & M32


def one_bit_coz(yuk: str, genislik: int, yukseklik: int) -> np.ndarray:
    """'!' ile başlayan one_bit yükünü (yukseklik, genislik) 0/1 dizisine çözer."""
    if not yuk.startswith("!"):
        raise ValueError("one_bit maske '!' ile başlamalı")
    d = _AralikCozucu(_ac(yuk[1:]))
    sayac = [1] * (BAGLAM * 2)
    pg = genislik + 2 * DOLGU
    r = bytearray(pg * (yukseklik + DOLGU))
    cikti = np.zeros((yukseklik, genislik), dtype=np.uint8)
    for y in range(yukseklik):
        satir = (y + DOLGU) * pg + DOLGU
        for x in range(genislik):
            p = satir + x
            q, e = p - pg, p - 2 * pg
            bag = (r[p - 1] | (r[p - 2] << 1) | (r[q - 2] << 2) | (r[q - 1] << 3) | (r[q] << 4)
                   | (r[q + 1] << 5) | (r[q + 2] << 6) | (r[e - 2] << 7) | (r[e - 1] << 8)
                   | (r[e] << 9) | (r[e + 1] << 10) | (r[e + 2] << 11))
            o = bag << 1
            sifir, bir = sayac[o], sayac[o + 1]
            bit = 0 if d.frekans(sifir + bir) < sifir else 1
            if bit:
                d.coz(sifir, bir)
            else:
                d.coz(0, sifir)
            r[p] = bit
            if bit:
                cikti[y, x] = 1
            sayac[o + bit] += ARTIS
            if sayac[o] + sayac[o + 1] >= SAYI_SINIRI:
                sayac[o] = sayac[o] >> 1 or 1
                sayac[o + 1] = sayac[o + 1] >> 1 or 1
    return cikti


def maskeler(metin: str) -> list[dict]:
    """SAM çıktı satırındaki her kayıt için tam kare boyutunda maske ve kutu."""
    sonuc = []
    for oid, x1, y1, x2, y2, w, h, c, mh, mw, yuk in KAYIT.findall(metin):
        x1, y1, x2, y2, w, h, mh, mw = map(int, (x1, y1, x2, y2, w, h, mh, mw))
        kare = np.zeros((h, w), dtype=np.uint8)
        kare[y1:y1 + mh, x1:x1 + mw] = one_bit_coz(yuk, mw, mh)
        sonuc.append({"id": int(oid), "kutu": (x1, y1, x2, y2), "guven": float(c) if c else None, "maske": kare})
    return sonuc
