"""Contracts for NEXO phases 23-30.

Small deterministic boundaries that can be tested independently of the model.
"""
from __future__ import annotations
import hashlib, json, re, time, uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable

class KnowledgeState(str, Enum):
    KNOW = "SÉ"
    CAN_RESEARCH = "PUEDO_INVESTIGAR"
    UNDETERMINED = "NO PUEDO DETERMINARLO"

@dataclass(frozen=True, slots=True)
class ErrorEvent:
    code: str
    message: str
    retryable: bool = False
    request_id: str = ""

@dataclass(frozen=True, slots=True)
class RequestCycle:
    steps: tuple[str, ...] = (
        "receive","validate","load_context","search_memory","detect_currentness",
        "detect_tools","select_model","execute_tools","verify","generate",
        "store_memory","deliver",
    )
    def validate(self) -> bool:
        return len(self.steps) == 12 and self.steps[0] == "receive" and self.steps[-1] == "deliver"

@dataclass(frozen=True, slots=True)
class Research:
    question: str
    sources: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    confidence: float | None = None
    created_at: float = field(default_factory=time.time)
    summary: str = ""

class VerificationPolicy:
    CURRENT_MARKERS = ("actual","actualmente","hoy","ahora","latest","current","precio","noticia","fuente","verifica","investiga")
    def requires_research(self, text: str) -> bool:
        value = (text or "").lower()
        return any(marker in value for marker in self.CURRENT_MARKERS)
    def state(self, *, has_answer: bool, can_research: bool, verified: bool) -> KnowledgeState:
        if verified and has_answer: return KnowledgeState.KNOW
        if can_research: return KnowledgeState.CAN_RESEARCH
        return KnowledgeState.UNDETERMINED

@dataclass(slots=True)
class CacheEntry:
    value: Any
    created_at: float
    ttl_seconds: float
    @property
    def expired(self) -> bool:
        return time.time() >= self.created_at + self.ttl_seconds

class TTLCache:
    def __init__(self) -> None:
        self._items: dict[str, CacheEntry] = {}
    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        if ttl_seconds <= 0: raise ValueError("ttl_seconds_must_be_positive")
        self._items[str(key)] = CacheEntry(value, time.time(), float(ttl_seconds))
    def get(self, key: str) -> Any | None:
        item = self._items.get(str(key))
        if item is None: return None
        if item.expired:
            self._items.pop(str(key), None); return None
        return item.value
    def clear(self) -> None:
        self._items.clear()

_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;]+"),
)
def redact_secrets(value: str) -> str:
    clean = str(value or "")
    for pattern in _SECRET_PATTERNS:
        clean = pattern.sub(lambda m: m.group(1) + "[REDACTED]", clean)
    return clean

@dataclass(frozen=True, slots=True)
class PrivacyPolicy:
    allowed_context_fields: tuple[str, ...] = ("message","relevant_memory","research")
    blocked_fields: tuple[str, ...] = ("api_key","token","password","secret","session")
    def minimize(self, context: dict[str, Any]) -> dict[str, Any]:
        return {key: context[key] for key in self.allowed_context_fields if key in context}

@dataclass(frozen=True, slots=True)
class ExportBundle:
    version: str
    memory: tuple[dict[str, Any], ...]
    preferences: dict[str, Any]
    research: tuple[dict[str, Any], ...]
    configuration: dict[str, Any]
    metadata: dict[str, Any]
    checksum: str
    @staticmethod
    def build(*, memory: list[dict[str, Any]], preferences: dict[str, Any], research: list[dict[str, Any]], configuration: dict[str, Any], metadata: dict[str, Any]) -> "ExportBundle":
        payload={"version":"1","memory":memory,"preferences":preferences,"research":research,"configuration":configuration,"metadata":metadata}
        canonical=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":"))
        return ExportBundle("1",tuple(memory),dict(preferences),tuple(research),dict(configuration),dict(metadata),hashlib.sha256(canonical.encode()).hexdigest())
    def to_dict(self) -> dict[str, Any]: return asdict(self)
    def verify(self) -> bool:
        payload={"version":self.version,"memory":list(self.memory),"preferences":self.preferences,"research":list(self.research),"configuration":self.configuration,"metadata":self.metadata}
        canonical=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":"))
        return hashlib.sha256(canonical.encode()).hexdigest()==self.checksum

@dataclass(frozen=True, slots=True)
class TrustEvent:
    event_id: str
    request_id: str
    action: str
    reason: str
    tool: str | None = None
    source: str | None = None
    model: str | None = None
    @classmethod
    def create(cls, request_id: str, action: str, reason: str, **kwargs: Any) -> "TrustEvent":
        return cls(uuid.uuid4().hex,request_id,action,reason,**kwargs)

class NexoProtocol:
    VERSION="1"
    KINDS={"Request","Tool","Memory","Provider","Event","Source"}
    @classmethod
    def envelope(cls, kind: str, payload: dict[str, Any], *, request_id: str | None = None) -> dict[str, Any]:
        if kind not in cls.KINDS: raise ValueError("unsupported_nexo_protocol_kind")
        return {"protocol":"NEXO","version":cls.VERSION,"kind":kind,"request_id":request_id or uuid.uuid4().hex,"payload":payload}

class BoundedOrchestrator:
    def __init__(self, max_steps: int = 8) -> None:
        if max_steps < 1: raise ValueError("max_steps_must_be_positive")
        self.max_steps=max_steps
    async def run(self, operations: list[Callable[[], Any]]) -> list[Any]:
        import inspect
        results=[]
        for index,operation in enumerate(operations):
            if index >= self.max_steps: raise RuntimeError("orchestrator_step_budget_exhausted")
            value=operation()
            if inspect.isawaitable(value): value=await value
            results.append(value)
        return results
