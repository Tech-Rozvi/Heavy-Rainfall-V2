"""Blocked temporal and spatial hold-out utilities."""
from __future__ import annotations

from typing import Iterator, Optional

import numpy as np


def blocked_temporal_splits(
    n_timesteps: int,
    n_folds: int = 5,
    min_train_frac: float = 0.5,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """
    Contiguous temporal blocks for cross-validation (no random shuffling).

    Yields (train_indices, test_indices) for each fold.
    """
    if n_folds < 2:
        raise ValueError("n_folds must be >= 2")
    block_size = n_timesteps // n_folds
    if block_size < 1:
        raise ValueError("Not enough timesteps for the requested folds")
    indices = np.arange(n_timesteps)
    for k in range(n_folds):
        test_start = k * block_size
        test_end = (k + 1) * block_size if k < n_folds - 1 else n_timesteps
        test_idx = indices[test_start:test_end]
        train_idx = np.concatenate([indices[:test_start], indices[test_end:]])
        if len(train_idx) / n_timesteps < min_train_frac:
            continue
        yield train_idx, test_idx


def spatial_holdout_mask(
    ny: int,
    nx: int,
    holdout_frac: float = 0.2,
    random_seed: int = 42,
) -> np.ndarray:
    """
    Boolean mask (True = hold-out) using spatial blocks rather than random pixels.
    """
    from sklearn.cluster import KMeans
    n_blocks = max(5, int(1 / holdout_frac))
    rows, cols = np.indices((ny, nx))
    coords = np.column_stack([rows.ravel(), cols.ravel()])
    km = KMeans(n_clusters=n_blocks, random_state=random_seed, n_init=10)
    labels = km.fit_predict(coords).reshape(ny, nx)
    # Hold out the first ceil(holdout_frac * n_blocks) clusters
    n_hold = max(1, int(np.ceil(holdout_frac * n_blocks)))
    return np.isin(labels, np.arange(n_hold))
