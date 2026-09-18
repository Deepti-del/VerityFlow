from __future__ import annotations

from typing import Any

from formula_utils import extract_formula_columns


PROFILE_SECTIONS = ("required_source", "derivable", "optional", "reference")


def _metric_key(metric: dict[str, Any]) -> str | None:
    return metric.get("output_column") or metric.get("metric_name")


def _metric_label(metric: dict[str, Any], key: str) -> str:
    return metric.get("metric_name") or key


def build_formula_relationship_graph(profile: dict[str, Any] | None) -> dict[str, Any]:
    """
    Build a deterministic KPI dependency graph from the active calculation profile.

    The graph is derived only from configured metric definitions and formulas.
    It does not calculate KPI values and does not infer domain relationships that
    the analyst has not encoded through formulas.
    """
    profile = profile or {}
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for section in PROFILE_SECTIONS:
        for metric in profile.get(section, []) or []:
            key = _metric_key(metric)
            if not key:
                continue
            nodes[key] = {
                "metric": key,
                "label": _metric_label(metric, key),
                "category": section,
                "unit": metric.get("unit"),
                "approved_by_analyst": bool(metric.get("approved_by_analyst")),
                "scope": metric.get("scope"),
                "has_formula": bool((metric.get("formula") or "").strip()),
            }

    for metric in profile.get("derivable", []) or []:
        target = _metric_key(metric)
        formula = (metric.get("formula") or "").strip()
        if not target or not formula:
            continue
        try:
            dependencies = sorted(extract_formula_columns(formula))
        except SyntaxError as exc:
            warnings.append({
                "metric": target,
                "reason": "invalid_formula_syntax",
                "message": (
                    f"Could not parse formula relationship for {target}: {exc.msg}."
                ),
            })
            continue

        nodes.setdefault(target, {
            "metric": target,
            "label": metric.get("metric_name") or target,
            "category": "derivable",
            "unit": metric.get("unit"),
            "approved_by_analyst": bool(metric.get("approved_by_analyst")),
            "scope": metric.get("scope"),
            "has_formula": True,
        })

        for dependency in dependencies:
            nodes.setdefault(dependency, {
                "metric": dependency,
                "label": dependency,
                "category": "formula_input",
                "unit": None,
                "approved_by_analyst": False,
                "scope": None,
                "has_formula": False,
            })
            edges.append({
                "source": dependency,
                "target": target,
                "relationship": "formula_dependency",
                "formula": formula,
                "approved_by_analyst": bool(metric.get("approved_by_analyst")),
                "scope": metric.get("scope"),
            })

    dependency_map: dict[str, list[str]] = {}
    downstream_map: dict[str, list[str]] = {}
    for edge in edges:
        dependency_map.setdefault(edge["target"], []).append(edge["source"])
        downstream_map.setdefault(edge["source"], []).append(edge["target"])

    return {
        "valid": True,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": list(nodes.values()),
        "edges": edges,
        "dependencies": {
            metric: sorted(set(dependencies))
            for metric, dependencies in dependency_map.items()
        },
        "downstream": {
            metric: sorted(set(targets))
            for metric, targets in downstream_map.items()
        },
        "warnings": warnings,
    }
