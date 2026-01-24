
from __future__ import annotations

from typing import List, Optional
from openai import OpenAI


class EmbeddingsClient:
    def __init__(self, api_key: str, model: str, dimensions: Optional[int]):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.dimensions = dimensions

    def embed_one(self, text: str) -> List[float]:
        text = (text or "").replace("\n", " ").strip()
        if not text:
            return []
        kwargs = {"input": [text], "model": self.model}
        if self.dimensions:
            kwargs["dimensions"] = self.dimensions
        resp = self.client.embeddings.create(**kwargs)
        return resp.data[0].embedding
