"""
Sentence-embedding features as a scikit-learn transformer.

The SentenceTransformer model is loaded lazily and is not pickled, so pipelines
saved with joblib stay small; the model comes from the Hugging Face cache
(downloaded on first use) when a saved pipeline is loaded again.
"""

from functools import lru_cache

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_MAX_CACHE = 20000
_cache: dict = {}  # (model_name, text) -> vector; lets the pillar and disclosure models share encodings


@lru_cache(maxsize=2)
def load_model(model_name: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


class EmbeddingFeaturizer(BaseEstimator, TransformerMixin):
    def __init__(self, model_name: str = DEFAULT_MODEL, batch_size: int = 64):
        self.model_name = model_name
        self.batch_size = batch_size

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        texts = list(X)
        missing = [t for t in dict.fromkeys(texts) if (self.model_name, t) not in _cache]
        if missing:
            if len(_cache) + len(missing) > _MAX_CACHE:
                _cache.clear()
            vecs = load_model(self.model_name).encode(
                missing, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False)
            _cache.update({(self.model_name, t): v for t, v in zip(missing, vecs)})
        return np.vstack([_cache[(self.model_name, t)] for t in texts])
