"""SAM 3.1 (Meta Model API) ile tek karede nesne tespiti.

Video modu kare başına en fazla 16 nesne takip ettiği için kavşakta kareler
tek tek görsel olarak gönderilir; takip bizim tarafımızda yapılır.
"""

import base64
import os
import re
from dataclasses import dataclass

import cv2
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

KUTU = re.compile(r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=\d+;h=\d+(?:;c=([\d.]+))?\|>")


@dataclass
class Kutu:
    x1: int
    y1: int
    x2: int
    y2: int
    guven: float | None

    @property
    def merkez(self) -> tuple[float, float]:
        return (self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2


def istemci() -> OpenAI:
    load_dotenv()
    return OpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])


def tespit(client: OpenAI, kare: np.ndarray, kavram: str) -> list[Kutu]:
    """Karedeki tüm `kavram` örneklerinin kutularını döndürür."""
    ok, png = cv2.imencode(".png", kare)
    if not ok:
        raise ValueError("kare kodlanamadı")
    url = "data:image/png;base64," + base64.b64encode(png.tobytes()).decode()
    yanit = client.responses.create(
        model="sam-3.1",
        input=[{
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": kavram},
                {"type": "input_image", "image_url": url},
            ],
        }],
        metadata={"include_confidence": "true", "mask_encoding": "one_bit"},
    )
    return [
        Kutu(int(a), int(b), int(c), int(d), float(g) if g else None)
        for a, b, c, d, g in KUTU.findall(yanit.output_text)
    ]
