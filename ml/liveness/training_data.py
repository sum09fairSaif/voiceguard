"""Feeding preprocessed clips to the model: what to read, and how often.

The training set is lopsided: about 5 fakes to every real clip, and ASVspoof 5
alone is over half of it. Sampled as it is, the model would learn that most
clips are fake and mostly what ASVspoof 5 sounds like. So clips are drawn:

- half real and half fake, so neither answer is right by default;
- within each half, each dataset in proportion to the square root of its
  size, so the small ones (CodecFake's real clips, Common Voice) count for
  more than their share without being repeated over and over.
"""

import io
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
import torch
from torch.utils.data import Dataset, WeightedRandomSampler

import audio
from manifest import BONAFIDE

REAL = 1  # AASIST's convention: output 1 is "real", output 0 "fake"


def load_split(data_dir: Path, split: str) -> pd.DataFrame:
    df = pd.read_parquet(data_dir / "manifest.processed.parquet")
    return df[df["split"] == split].reset_index(drop=True)


def sampling_weights(df: pd.DataFrame) -> np.ndarray:
    """How likely each clip is to be drawn (they add up to 1)."""
    weights = np.zeros(len(df))
    for _, half in df.groupby("label"):
        sizes = half.groupby("source").size()
        share = np.sqrt(sizes) / np.sqrt(sizes).sum()
        per_clip = 0.5 * share / sizes
        weights[half.index] = half["source"].map(per_clip).to_numpy()
    return weights / weights.sum()


def balanced_sampler(df: pd.DataFrame, clips: int, seed: int) -> WeightedRandomSampler:
    """Draws clips (with replacement) according to sampling_weights."""
    generator = torch.Generator().manual_seed(seed)
    return WeightedRandomSampler(torch.from_numpy(sampling_weights(df)), clips, replacement=True,
                                 generator=generator)


def even_sample(df: pd.DataFrame, per_group: int, seed: int = 0) -> pd.DataFrame:
    """Up to per_group clips per dataset and label, the same ones every time."""
    sample = df.sample(frac=1, random_state=seed).groupby(["source", "label"]).head(per_group)
    return sample.reset_index(drop=True)


class ClipDataset(Dataset):
    """Preprocessed clips as AASIST input, with their labels.

    In training (augment given), each clip gives a random 4-second window and
    random augmentation, different every time it's drawn. Otherwise it's the
    first 4 seconds, unchanged, so scores can be repeated.
    """

    def __init__(self, df: pd.DataFrame, data_dir: Path, augment=None):
        if "shard" in df.columns:  # a pack made by kaggle_pack.py: clips inside a few big files
            self.paths = [(str(data_dir / s), int(o), int(n)) for s, o, n in zip(df["shard"], df["offset"], df["nbytes"])]
        else:
            self.paths = [str(data_dir / p) for p in df["path"]]
        self.labels = (df["label"] == BONAFIDE).astype(int).to_numpy()
        self.augment = augment
        self._rng = None

    def __len__(self) -> int:
        return len(self.paths)

    def rng(self) -> np.random.Generator:
        # One generator per DataLoader worker, seeded from torch's own seed for
        # that worker, so workers don't all draw the same random numbers.
        if self._rng is None:
            self._rng = np.random.default_rng(torch.initial_seed())
        return self._rng

    def read(self, index: int) -> np.ndarray:
        where = self.paths[index]
        if isinstance(where, tuple):
            shard, offset, nbytes = where
            with open(shard, "rb") as f:
                f.seek(offset)
                where = io.BytesIO(f.read(nbytes))
        samples, _ = sf.read(where, dtype="float32")
        return samples

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        samples = self.read(index)
        if self.augment is None:
            clip = audio.fix_length(samples)
        else:
            rng = self.rng()
            clip = audio.fix_length(self.augment(audio.fix_length(samples, rng), rng))
        return torch.from_numpy(np.ascontiguousarray(clip, dtype=np.float32)), int(self.labels[index])
