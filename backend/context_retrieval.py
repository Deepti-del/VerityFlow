"""Governed business-context retrieval for evidence-grounded narratives.

Operational data and KPI calculations never enter this layer.  The retriever
only receives approved context records plus a compact evidence query produced
by the deterministic pipeline.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from database import get_approved_context


load_dotenv()

DEFAULT_INDEX_NAME = "verityflow-approved-context"
IGNORED_EVIDENCE_KEYS = {"thresholds", "row_index", "date"}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", value.lower())
        if len(token) > 2
    }


def _document(item: dict) -> dict:
    return {
        "id": item["context_id"],
        "text": item["content"],
        "metadata": {
            "customer_id": item["customer_id"],
            "report_type": item["report_type"],
            "kpi": item.get("kpi") or "general",
            "context_type": item["context_type"],
            "source": item.get("source") or "approved_context",
            "version": str(item.get("version") or 1),
            "approval_status": "approved",
        },
    }


def _context_fingerprint(items: list[dict]) -> str:
    value = "|".join(
        f"{item['context_id']}:{item.get('version', 1)}:{item.get('updated_at', '')}"
        for item in sorted(items, key=lambda record: record["context_id"])
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def evidence_metrics(draft: dict) -> list[str]:
    metrics: list[str] = []
    for finding in draft.get("triggered_findings") or []:
        for key, value in (finding.get("evidence") or {}).items():
            if key not in IGNORED_EVIDENCE_KEYS and value is not None:
                metrics.append(key)
    if not metrics:
        metrics.extend((draft.get("latest_kpis") or {}).keys())
    return list(dict.fromkeys(metrics))


def build_evidence_packet(draft: dict) -> dict:
    findings = []
    for finding in draft.get("triggered_findings") or []:
        evidence = {
            key: value
            for key, value in (finding.get("evidence") or {}).items()
            if key != "row_index"
        }
        findings.append({
            "rule_name": finding.get("rule_name"),
            "severity": finding.get("severity"),
            "message": finding.get("message"),
            "suggestion": finding.get("suggestion"),
            "evidence": evidence,
        })
    return {
        "customer_id": draft.get("customer_id"),
        "report_type": draft.get("report_type"),
        "report_date": draft.get("report_date"),
        "kpis": evidence_metrics(draft),
        "latest_kpis": draft.get("latest_kpis") or {},
        "findings": findings,
    }


def build_retrieval_query(packet: dict) -> str:
    parts = [
        f"Customer {packet.get('customer_id')}",
        f"report type {packet.get('report_type')}",
    ]
    if packet.get("kpis"):
        parts.append("KPIs " + ", ".join(packet["kpis"]))
    for finding in packet.get("findings") or []:
        if finding.get("rule_name"):
            parts.append(str(finding["rule_name"]))
        if finding.get("message"):
            parts.append(str(finding["message"]))
        evidence_keys = [
            key for key in (finding.get("evidence") or {})
            if key not in IGNORED_EVIDENCE_KEYS
        ]
        if evidence_keys:
            parts.append("evidence " + ", ".join(evidence_keys))
    return ". ".join(parts)


@dataclass
class RetrievalResult:
    provider: str
    index_name: str
    documents: list[dict]
    retrieval_latency_ms: float
    warning: str | None = None


class ApprovedContextRetriever:
    """Moss-backed retriever with a clearly labelled local development mode."""

    def __init__(self) -> None:
        self.project_id = os.getenv("MOSS_PROJECT_ID", "").strip()
        self.project_key = os.getenv("MOSS_PROJECT_KEY", "").strip()
        self.index_name = os.getenv("MOSS_INDEX_NAME", DEFAULT_INDEX_NAME).strip()
        self.enabled = (
            os.getenv("MOSS_ENABLED", "true").lower() not in {"0", "false", "no"}
            and bool(self.project_id and self.project_key)
        )
        self._client = None
        self._loaded_fingerprint: str | None = None

    def _all_approved_documents(self) -> list[dict]:
        return get_approved_context(approved_only=True)

    async def _moss_client(self):
        if self._client is None:
            try:
                from moss import MossClient
            except ImportError as exc:
                raise RuntimeError(
                    "The moss package is not installed. Run pip install -r "
                    "backend/requirements.txt."
                ) from exc
            self._client = MossClient(self.project_id, self.project_key)
        return self._client

    async def sync(self) -> dict:
        items = self._all_approved_documents()
        if not items:
            return {
                "status": "no_approved_context",
                "provider": "moss" if self.enabled else "local_fallback",
                "index_name": self.index_name,
                "document_count": 0,
                "message": "No active analyst-approved context is available to index.",
            }
        if not self.enabled:
            return {
                "status": "local_fallback",
                "provider": "local_fallback",
                "index_name": self.index_name,
                "document_count": len(items),
                "message": "Set MOSS_PROJECT_ID and MOSS_PROJECT_KEY to sync the Moss index.",
            }

        fingerprint = _context_fingerprint(items)
        if self._loaded_fingerprint == fingerprint:
            return {
                "status": "ready",
                "provider": "moss",
                "index_name": self.index_name,
                "document_count": len(items),
                "message": "Moss index is loaded and current.",
            }

        client = await self._moss_client()
        document_payloads = [_document(item) for item in items]
        try:
            # Current Moss SDK releases require typed DocumentInfo values.
            # Keep the dictionary payload as a compatibility fallback for
            # earlier SDKs that accepted plain mappings.
            from moss import DocumentInfo

            documents = [
                DocumentInfo(
                    document["id"],
                    document["text"],
                    document["metadata"],
                )
                for document in document_payloads
            ]
        except ImportError:
            documents = document_payloads
        try:
            await client.get_index(self.index_name)
        except Exception:
            await client.create_index(self.index_name, documents)
        else:
            try:
                from moss import MutationOptions

                await client.add_docs(
                    self.index_name,
                    documents,
                    MutationOptions(upsert=True),
                )
            except (ImportError, TypeError):
                # Older SDK releases accept dictionaries and expose upsert as a
                # plain options mapping.
                await client.add_docs(
                    self.index_name,
                    documents,
                    {"upsert": True},
                )
        await client.load_index(self.index_name)
        self._loaded_fingerprint = fingerprint
        return {
            "status": "ready",
            "provider": "moss",
            "index_name": self.index_name,
            "document_count": len(items),
            "message": "Approved context synced and loaded into Moss.",
        }

    def _local_query(
        self,
        *,
        query: str,
        customer_id: str,
        report_type: str,
        kpis: list[str],
        top_k: int,
    ) -> RetrievalResult:
        start = time.perf_counter()
        candidates = get_approved_context(
            customer_id,
            report_type,
            kpis,
            approved_only=True,
        )
        query_tokens = _tokens(query)
        ranked = []
        for item in candidates:
            document_tokens = _tokens(
                " ".join([
                    item.get("content") or "",
                    item.get("context_type") or "",
                    item.get("kpi") or "",
                ])
            )
            overlap = len(query_tokens & document_tokens)
            specificity = 2 if item.get("kpi") in kpis else 1
            score = round((overlap + specificity) / max(len(query_tokens), 1), 4)
            ranked.append({
                "id": item["context_id"],
                "text": item["content"],
                "score": score,
                "metadata": _document(item)["metadata"],
            })
        ranked.sort(key=lambda item: item["score"], reverse=True)
        latency = round((time.perf_counter() - start) * 1000, 3)
        return RetrievalResult(
            provider="local_fallback",
            index_name=self.index_name,
            documents=ranked[:top_k],
            retrieval_latency_ms=latency,
            warning=(
                "Moss credentials are not configured. Results use a deterministic "
                "local fallback and must not be presented as Moss retrieval."
            ),
        )

    async def query(
        self,
        *,
        query: str,
        customer_id: str,
        report_type: str,
        kpis: list[str],
        top_k: int = 4,
    ) -> RetrievalResult:
        if not self.enabled:
            return self._local_query(
                query=query,
                customer_id=customer_id,
                report_type=report_type,
                kpis=kpis,
                top_k=top_k,
            )

        try:
            await self.sync()
            client = await self._moss_client()
            from moss import QueryOptions

            filters = {
                "$and": [
                    {"field": "customer_id", "condition": {"$eq": customer_id}},
                    {"field": "report_type", "condition": {"$eq": report_type}},
                    {"field": "approval_status", "condition": {"$eq": "approved"}},
                    {
                        "field": "kpi",
                        "condition": {"$in": list(dict.fromkeys(["general", *kpis]))},
                    },
                ]
            }
            started = time.perf_counter()
            result = await client.query(
                self.index_name,
                query,
                QueryOptions(top_k=top_k, filter=filters),
            )
            runtime_latency = round((time.perf_counter() - started) * 1000, 3)
            documents = []
            for doc in result.docs:
                documents.append({
                    "id": doc.id,
                    "text": doc.text,
                    "score": round(float(doc.score), 4),
                    "metadata": dict(doc.metadata or {}),
                })
            return RetrievalResult(
                provider="moss",
                index_name=self.index_name,
                documents=documents,
                retrieval_latency_ms=float(
                    getattr(result, "time_taken_ms", runtime_latency)
                ),
            )
        except Exception as exc:
            fallback = self._local_query(
                query=query,
                customer_id=customer_id,
                report_type=report_type,
                kpis=kpis,
                top_k=top_k,
            )
            fallback.warning = (
                f"Moss retrieval failed ({type(exc).__name__}). "
                "A labelled local fallback was used for this development run."
            )
            return fallback


def assemble_reviewable_narrative(packet: dict, documents: list[dict]) -> dict:
    """Assemble a reviewable draft without changing or inventing facts."""
    findings = packet.get("findings") or []
    if findings:
        primary = findings[0]
        parts = [
            primary.get("message")
            or f"{primary.get('rule_name', 'An approved rule')} was triggered."
        ]
        evidence = primary.get("evidence") or {}
        evidence_values = [
            f"{key} {value}"
            for key, value in evidence.items()
            if key not in IGNORED_EVIDENCE_KEYS and value is not None
        ]
        if evidence_values:
            parts.append("Calculated evidence: " + ", ".join(evidence_values) + ".")
    else:
        parts = [
            "No approved exception rule triggered for the selected report period."
        ]

    if documents:
        # The retrieved statement is visible separately in the UI, so an analyst
        # can verify exactly how context influenced the wording.
        parts.append(documents[0]["text"])

    return {
        "title": findings[0].get("rule_name") if findings else "Reporting context",
        "text": " ".join(part for part in parts if part),
        "status": "awaiting_analyst_approval",
        "evidence_count": len(findings),
        "context_ids": [document["id"] for document in documents],
    }


async def ground_report_draft(
    draft: dict,
    retriever: ApprovedContextRetriever | None = None,
) -> dict:
    started = time.perf_counter()
    packet = build_evidence_packet(draft)
    query = build_retrieval_query(packet)
    retriever = retriever or default_retriever
    result = await retriever.query(
        query=query,
        customer_id=packet["customer_id"],
        report_type=packet["report_type"],
        kpis=packet["kpis"],
    )
    return {
        "status": "ready" if result.documents else "no_approved_context",
        "provider": result.provider,
        "index_name": result.index_name,
        "query": query,
        "filters": {
            "customer_id": packet["customer_id"],
            "report_type": packet["report_type"],
            "kpis": ["general", *packet["kpis"]],
            "approval_status": "approved",
        },
        "retrieval_latency_ms": round(result.retrieval_latency_ms, 3),
        "pipeline_latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "warning": result.warning,
        "evidence_packet": packet,
        "retrieved_context": result.documents,
        "reviewable_narrative": assemble_reviewable_narrative(
            packet,
            result.documents,
        ),
    }


default_retriever = ApprovedContextRetriever()
