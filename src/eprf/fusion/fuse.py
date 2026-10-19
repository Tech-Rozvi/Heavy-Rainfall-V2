"""
Multi-source rainfall fusion.

Design principles
-----------------
- Do not silently average incompatible products.
- Prefer methods that can be justified by validation (see bias benchmark).
- Gauge, where present and finite, can optionally override or anchor fusion.
- All fusion outputs are labelled data_kind-compatible (fused / estimated).

Implemented methods (intentionally few and transparent):
- mean: unweighted mean of finite members
- weighted_mean: user- or skill-supplied weights (must sum ~1)
- gauge_priority: use gauge where finite, else mean of others
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

import numpy as np

from src.eprf.fusion.products import ProductCollection, RainfallProduct
from src.utils import get_logger

logger = get_logger(__name__)


class FusionMethod(str, Enum):
    MEAN = "mean"
    WEIGHTED_MEAN = "weighted_mean"
    GAUGE_PRIORITY = "gauge_priority"


@dataclass
class FusionResult:
    method: str
    fused: np.ndarray
    members_used: list[str]
    weights: dict[str, float]
    notes: list[str] = field(default_factory=list)
    product: Optional[RainfallProduct] = None

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "members_used": self.members_used,
            "weights": self.weights,
            "notes": self.notes,
            "shape": list(np.asarray(self.fused).shape),
            "product_meta": self.product.to_meta_dict() if self.product else None,
        }


def fuse_products(
    collection: ProductCollection,
    *,
    method: FusionMethod = FusionMethod.MEAN,
    weights: Optional[dict[str, float]] = None,
    gauge_name: Optional[str] = None,
    require_at_least: int = 1,
) -> FusionResult:
    """
    Fuse aligned rainfall products in a ProductCollection.

    Arrays must be broadcastable to a common shape (caller is responsible
    for spatial/temporal alignment before fusion).
    """
    if not collection.products:
        raise ValueError("ProductCollection is empty")

    names = list(collection.products.keys())
    arrays = [np.asarray(collection.products[n].data, dtype="float64") for n in names]
    # Broadcast to common shape
    try:
        common = np.broadcast_shapes(*[a.shape for a in arrays])
    except ValueError as exc:
        raise ValueError(
            "Products are not broadcast-compatible; align spatially/temporally first."
        ) from exc
    stacked = np.stack([np.broadcast_to(a, common).astype("float64") for a in arrays], axis=0)

    notes: list[str] = []
    if collection.alignment_note:
        notes.append(collection.alignment_note)

    w = np.ones(len(names), dtype="float64")
    if method == FusionMethod.WEIGHTED_MEAN:
        if not weights:
            notes.append("weighted_mean requested without weights; using equal weights.")
        else:
            w = np.array([float(weights.get(n, 0.0)) for n in names], dtype="float64")
            if w.sum() <= 0:
                raise ValueError("Weights sum to zero")
            w = w / w.sum()

    if method == FusionMethod.GAUGE_PRIORITY:
        gname = gauge_name
        if gname is None:
            # Heuristic: product kind == gauge
            for n, p in collection.products.items():
                if p.kind == "gauge":
                    gname = n
                    break
        if gname is None or gname not in collection.products:
            notes.append("No gauge product found; falling back to mean.")
            method = FusionMethod.MEAN
        else:
            g = np.broadcast_to(
                np.asarray(collection.products[gname].data, dtype="float64"), common
            )
            # Mean of non-gauge members
            other_idx = [i for i, n in enumerate(names) if n != gname]
            if other_idx:
                others = stacked[other_idx]
                with np.errstate(all="ignore"):
                    fill = np.nanmean(others, axis=0)
            else:
                fill = np.full(common, np.nan)
            fused = np.where(np.isfinite(g), g, fill)
            weight_map = {n: (1.0 if n == gname else 0.0) for n in names}
            notes.append(f"Gauge priority using '{gname}' where finite.")
            product = RainfallProduct(
                name="fused_gauge_priority",
                kind="fused",
                data=fused,
                notes=notes,
            )
            return FusionResult(
                method=FusionMethod.GAUGE_PRIORITY.value,
                fused=fused,
                members_used=names,
                weights=weight_map,
                notes=notes,
                product=product,
            )

    # mean / weighted_mean
    # Mask-aware weighted average
    finite = np.isfinite(stacked)
    n_finite = finite.sum(axis=0)
    if require_at_least > 1:
        notes.append(f"require_at_least={require_at_least} members for a fused pixel")
    w_b = w.reshape([-1] + [1] * len(common))
    stacked_filled = np.where(finite, stacked, 0.0)
    w_eff = np.where(finite, w_b, 0.0)
    w_sum = w_eff.sum(axis=0)
    with np.errstate(all="ignore"):
        fused = np.where(w_sum > 0, (stacked_filled * w_eff).sum(axis=0) / w_sum, np.nan)
    if require_at_least > 1:
        fused = np.where(n_finite >= require_at_least, fused, np.nan)

    weight_map = {n: float(w[i]) for i, n in enumerate(names)}
    product = RainfallProduct(
        name=f"fused_{method.value}",
        kind="fused",
        data=fused,
        notes=notes,
    )
    logger.info("Fused %d products via %s", len(names), method.value)
    return FusionResult(
        method=method.value,
        fused=fused,
        members_used=names,
        weights=weight_map,
        notes=notes,
        product=product,
    )
