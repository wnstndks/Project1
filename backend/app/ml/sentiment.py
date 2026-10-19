"""Headline sentiment. FinBERT is a BERT model fine-tuned on financial news (ProsusAI/finbert)."""

import threading
from dataclasses import dataclass
from typing import Protocol

FINBERT_MODEL = "ProsusAI/finbert"


@dataclass(frozen=True)
class Sentiment:
    positive: float
    negative: float
    neutral: float

    @property
    def score(self) -> float:
        """In [-1, 1]: positive minus negative probability."""
        return self.positive - self.negative


class SentimentScorer(Protocol):
    def score(self, texts: list[str]) -> list[Sentiment]: ...


class FinBertScorer:
    """Loads the model on first use (~20 s, ~440 MB download the very first time)."""

    def __init__(self, model: str = FINBERT_MODEL, batch_size: int = 32) -> None:
        self.model = model
        self.batch_size = batch_size
        self._pipeline = None
        self._lock = threading.Lock()

    def score(self, texts: list[str]) -> list[Sentiment]:
        if not texts:
            return []
        pipe = self._load()
        results = pipe(texts, batch_size=self.batch_size, truncation=True, max_length=128)
        out = []
        for labels in results:
            probs = {d["label"].lower(): float(d["score"]) for d in labels}
            out.append(
                Sentiment(
                    probs.get("positive", 0.0),
                    probs.get("negative", 0.0),
                    probs.get("neutral", 0.0),
                )
            )
        return out

    def _load(self):
        with self._lock:
            if self._pipeline is None:
                # Imported lazily: transformers is in the optional `ml` dependency group.
                from transformers import pipeline

                self._pipeline = pipeline(
                    "text-classification", model=self.model, top_k=None, device=-1
                )
            return self._pipeline


class KeywordScorer:
    """Tiny deterministic stand-in for tests and CI (no model download)."""

    POSITIVE = ("surge", "beat", "record", "rally", "upgrade", "soar", "gain")
    NEGATIVE = ("fall", "miss", "probe", "plunge", "downgrade", "lawsuit", "drop")

    def score(self, texts: list[str]) -> list[Sentiment]:
        out = []
        for t in texts:
            low = t.lower()
            pos = any(w in low for w in self.POSITIVE)
            neg = any(w in low for w in self.NEGATIVE)
            if pos and not neg:
                out.append(Sentiment(0.8, 0.1, 0.1))
            elif neg and not pos:
                out.append(Sentiment(0.1, 0.8, 0.1))
            else:
                out.append(Sentiment(0.1, 0.1, 0.8))
        return out
