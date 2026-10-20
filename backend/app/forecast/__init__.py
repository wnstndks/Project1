"""Forecasting engine v2: a pooled gradient-boosted quantile model over many assets.

Pipeline: `panel` (point-in-time features and targets for every asset and date) →
`cv` (purged walk-forward splits) → `models` (baselines and the GBDT) → `walkforward`
(out-of-sample predictions, conformal calibration) → `metrics`/`report` (skill against
baselines, significance tests and the "edge" verdict).

Everything here is pure: data comes in as DataFrames and nothing touches the database
or the network, so the whole pipeline is tested on synthetic series.
"""
