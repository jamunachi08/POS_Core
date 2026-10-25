"""Demand forecasting engine — statistical, explainable, dependency-free.

Every number the planner shows comes from here, never from a language model.
Per item and outlet it:

1. Builds a zero-filled daily series from posted POS sales (returns net off).
2. Learns weekday seasonality (Saudi Fri/Sat weekend included) from recent
   weeks, shrunk toward 1.0 so a thin history cannot produce wild indices.
3. Learns an uplift for each calendar event it has seen (Ramadan, Eid,
   payday, …), shrunk by how many event days it saw. An event never seen
   uses the prior from AlphaX POS Calendar Event, else no adjustment.
4. Smooths the de-seasonalised level (exponential smoothing), or uses
   Croston-SBA when an item sells on fewer than half the days.
5. Back-tests itself on the last two weeks against a seasonal-naive
   forecast and keeps whichever was more accurate, item by item.
6. Puts an interval around each forecast from its own back-test residuals.

The output carries the method and the drivers, so a kitchen manager can see
why tomorrow says 140 shawarma and not 90.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

Z = {"P50": 0.0, "P80": 0.8416, "P90": 1.2816}


@dataclass
class ItemForecast:
	item_code: str
	target: date
	qty: float
	low: float
	high: float
	method: str
	backtest_wape: float | None
	drivers: list[str] = field(default_factory=list)

	def planned(self, plan_to: str) -> float:
		if plan_to == "P50":
			return self.qty
		sigma = max(self.high - self.qty, 0.0) / Z["P90"] if self.high > self.qty else 0.0
		return self.qty + Z.get(plan_to, 0.0) * sigma


def _weekday_index(series: dict[date, float], end: date, weeks: int = 8, shrink: float = 4.0) -> dict[int, float]:
	start = end - timedelta(days=7 * weeks - 1)
	by_wd: dict[int, list[float]] = {i: [] for i in range(7)}
	values = []
	for i in range((end - start).days + 1):
		d = start + timedelta(days=i)
		v = series.get(d, 0.0)
		by_wd[d.weekday()].append(v)
		values.append(v)
	overall = sum(values) / len(values) if values else 0.0
	if overall <= 0:
		return {i: 1.0 for i in range(7)}
	idx = {}
	for wd, vals in by_wd.items():
		n = len(vals)
		raw = (sum(vals) / n) / overall if n else 1.0
		idx[wd] = (raw * n + 1.0 * shrink) / (n + shrink)
	mean = sum(idx.values()) / 7
	return {k: v / mean for k, v in idx.items()}


def _event_uplifts(series, events_by_day, weekday_idx, start, end, priors, min_days=3, shrink=5.0):
	"""Ratio of actual to weekday-expected demand on tagged days vs. untagged neighbours."""
	base_vals = []
	tag_ratios: dict[str, list[float]] = {}
	d = start
	window = []
	while d <= end:
		v = series.get(d, 0.0)
		exp_wd = weekday_idx.get(d.weekday(), 1.0)
		tags = events_by_day.get(d, set())
		if not tags:
			window.append(v / exp_wd if exp_wd else v)
			window = window[-28:]
		elif window:
			base = sum(window) / len(window)
			if base > 0:
				for t in tags:
					tag_ratios.setdefault(t, []).append((v / exp_wd) / base)
		d += timedelta(days=1)
	uplifts = {}
	for t, ratios in tag_ratios.items():
		if len(ratios) < min_days:
			continue
		r = median(ratios)
		n = len(ratios)
		prior = priors.get(t, 1.0)
		uplifts[t] = (r * n + prior * shrink) / (n + shrink)
	for t, p in priors.items():
		uplifts.setdefault(t, p)
	return uplifts


def _event_factor(tags, uplifts, drivers=None):
	f = 1.0
	for t in sorted(tags):
		u = uplifts.get(t)
		if u and abs(u - 1.0) > 0.02:
			f *= u
			if drivers is not None:
				drivers.append(f"{t} ×{u:.2f}")
	return f


def _ses_level(values: list[float], alpha: float = 0.3) -> float:
	if not values:
		return 0.0
	level = values[0]
	for v in values[1:]:
		level = alpha * v + (1 - alpha) * level
	return level


def _croston_sba(values: list[float], alpha: float = 0.15) -> float:
	nz = [(i, v) for i, v in enumerate(values) if v > 0]
	if not nz:
		return 0.0
	z = nz[0][1]
	p = nz[0][0] + 1
	last = nz[0][0]
	for i, v in nz[1:]:
		z = alpha * v + (1 - alpha) * z
		p = alpha * (i - last) + (1 - alpha) * p
		last = i
	return (1 - alpha / 2) * z / max(p, 1.0)


def _predict(series, events_by_day, history_end, target, priors, drivers=None, weeks=8):
	"""One forecast for `target` using only data up to `history_end`."""
	wd_idx = _weekday_index(series, history_end, weeks=weeks)
	hist_start = min(series) if series else history_end
	uplifts = _event_uplifts(series, events_by_day, wd_idx, hist_start, history_end, priors)
	recent_days = [history_end - timedelta(days=i) for i in range(55, -1, -1)]
	deseason = []
	zeros = 0
	for d in recent_days:
		v = series.get(d, 0.0)
		if v <= 0:
			zeros += 1
		f = wd_idx.get(d.weekday(), 1.0) * _event_factor(events_by_day.get(d, set()), uplifts)
		deseason.append(v / f if f else v)
	intermittent = zeros > len(recent_days) / 2
	level = _croston_sba(deseason) if intermittent else _ses_level(deseason)
	ev = _event_factor(events_by_day.get(target, set()), uplifts, drivers)
	wd = wd_idx.get(target.weekday(), 1.0)
	if drivers is not None and abs(wd - 1.0) > 0.05:
		drivers.insert(0, f"{target.strftime('%A')} ×{wd:.2f}")
	method = "Croston SBA" if intermittent else "Seasonal ES"
	if ev != 1.0:
		method += " + events"
	return max(level * wd * ev, 0.0), method


def _seasonal_naive(series, history_end, target):
	"""Same weekday last week, averaged over the last four weeks."""
	vals = []
	d = target - timedelta(days=7)
	while len(vals) < 4:
		while d > history_end:
			d -= timedelta(days=7)
		vals.append(series.get(d, 0.0))
		d -= timedelta(days=7)
	return sum(vals) / len(vals)


def forecast_item(
	item_code: str,
	series: dict[date, float],
	events_by_day: dict[date, set[str]],
	history_end: date,
	targets: list[date],
	priors: dict[str, float] | None = None,
	backtest_days: int = 14,
) -> list[ItemForecast]:
	priors = priors or {}
	# --- back-test: refit at each holdout day, compare with seasonal naive
	model_err, naive_err, actual_sum = 0.0, 0.0, 0.0
	residuals = []
	for k in range(backtest_days, 0, -1):
		t = history_end - timedelta(days=k - 1)
		cutoff = t - timedelta(days=1)
		actual = series.get(t, 0.0)
		pred, _ = _predict(series, events_by_day, cutoff, t, priors)
		naive = _seasonal_naive(series, cutoff, t)
		model_err += abs(actual - pred)
		naive_err += abs(actual - naive)
		actual_sum += actual
		residuals.append(actual - pred)
	use_naive = actual_sum > 0 and naive_err < model_err * 0.95
	wape = (min(model_err, naive_err) if use_naive else model_err) / actual_sum if actual_sum else None
	sigma = math.sqrt(sum(r * r for r in residuals) / len(residuals)) if residuals else 0.0

	out = []
	for t in targets:
		drivers: list[str] = []
		qty, method = _predict(series, events_by_day, history_end, t, priors, drivers)
		if use_naive:
			qty = _seasonal_naive(series, history_end, t)
			method = "Seasonal naive"
			drivers = [f"same weekday, last 4 weeks (beat the model in back-test)"]
		horizon = (t - history_end).days
		s = sigma * math.sqrt(max(horizon, 1) ** 0.5)
		out.append(
			ItemForecast(
				item_code=item_code,
				target=t,
				qty=round(qty, 2),
				low=round(max(qty - Z["P90"] * s, 0.0), 2),
				high=round(qty + Z["P90"] * s, 2),
				method=method,
				backtest_wape=round(wape, 4) if wape is not None else None,
				drivers=drivers,
			)
		)
	return out


def hourly_profile(hour_counts: dict[int, float]) -> dict[int, float]:
	total = sum(hour_counts.values())
	if total <= 0:
		return {}
	return {h: v / total for h, v in sorted(hour_counts.items())}


def prep_slots(profile: dict[int, float], slots=((0, 11, "Morning"), (11, 16, "Lunch"), (16, 24, "Evening"))):
	"""Share of the day's demand falling in each prep slot."""
	if not profile:
		return {name: (1.0 if i == 0 else 0.0) for i, (_, _, name) in enumerate(slots)}
	return {name: round(sum(v for h, v in profile.items() if a <= h < b), 4) for a, b, name in slots}


def wape(pairs: list[tuple[float, float]]) -> float | None:
	act = sum(a for a, _ in pairs)
	if act <= 0:
		return None
	return sum(abs(a - f) for a, f in pairs) / act


def bias(pairs: list[tuple[float, float]]) -> float | None:
	act = sum(a for a, _ in pairs)
	if act <= 0:
		return None
	return (sum(f for _, f in pairs) - act) / act
