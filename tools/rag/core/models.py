from __future__ import annotations
from dataclasses import dataclass, field
from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict

import operator

@dataclass
class RawDocument:
    """A raw text unit before chunking."""
    doc_id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Domain tag used to route to the correct collection
    domain: str = "porto"   # "porto" | "wisudawan"


@dataclass
class Chunk:
    """A processed, chunk-level unit ready for embedding."""
    chunk_id: str
    doc_id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    domain: str = "porto"
    embedding: Optional[List[float]] = None
    sparse_indices: Optional[List[int]] = None
    sparse_values: Optional[List[float]] = None


@dataclass
class RetrievedChunk:
    """A chunk returned by the retriever with a relevance score."""
    chunk_id: str
    doc_id: str
    text: str
    metadata: Dict[str, Any]
    score: float                    # fused or reranked score
    dense_score: float = 0.0
    sparse_score: float = 0.0


@dataclass
class RetrievalResult:
    """Container for a single retrieval call."""
    query: str
    chunks: List[RetrievedChunk] = field(default_factory=list)
    is_relevant: bool = True        # after relevance check
    reformulated_query: Optional[str] = None
    attempt: int = 1


@dataclass
class SubTask:
    """A decomposed sub-task produced by the agent planner."""
    task_id: int
    description: str
    # "rag" | "sql" — agent decides which tool to call
    tool: str = "rag"
    query: str = ""
    # For porto agent: intermediate result
    result: Optional[str] = None
    # Whether this sub-task's result already satisfies the original query
    is_sufficient: bool = False


@dataclass
class AgentContext:
    """Shared context passed through an agent's execution."""
    original_query: str
    tasks: List[SubTask] = field(default_factory=list)
    retrieved_chunks: List[RetrievedChunk] = field(default_factory=list)
    final_answer: Optional[str] = None
    # Role-based access
    user_id: Optional[str] = None
    user_role: Optional[str] = None


@dataclass
class RAGASScores:
    """RAGAS evaluation scores for a single RAG output."""
    faithfulness: float = 0.0       # Is answer grounded in context?
    context_relevance: float = 0.0  # Are retrieved chunks relevant to query?
    answer_relevance: float = 0.0   # Does answer address the query?
    passed: bool = False

    def __post_init__(self):
        self.passed = (
            self.faithfulness >= 0.7
            and self.context_relevance >= 0.5
            and self.answer_relevance >= 0.6
        )


@dataclass
class RAGOutput:
    """Final output of the RAG pipeline for one query."""
    query: str
    answer: str
    retrieved_chunks: List[RetrievedChunk]
    scores: Optional[RAGASScores] = None
    retry_count: int = 0
    sub_tasks: List[SubTask] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PortoAgentState(TypedDict, total=False):
    """
    State object threaded through the Porto agent's StateGraph.

    The Porto graph has a sequential-with-early-exit topology:
      decompose → [execute_task → check_sufficiency] loop → synthesise → evaluate
    """
    # Input
    original_query: str
    user_id: Optional[str]
    user_role: Optional[str]
    metadata_filter: Optional[Dict[str, Any]]

    # Planner output
    tasks: List[SubTask]
    current_task_index: int             # pointer for the sequential loop

    # Accumulator — reducer appends from each task node
    retrieved_chunks: Annotated[List[RetrievedChunk], operator.add]
    task_results: Annotated[List[str], operator.add]

    # Step-reasoner signal
    is_sufficient: bool

    # Generation
    answer: str

    # Evaluation / retry
    ragas_scores: Optional[RAGASScores]
    retry_count: int
    reformulated_query: Optional[str]   # set by evaluator node on retry


class WisudawanAgentState(TypedDict, total=False):
    # Input
    original_query: str
    user_id: Optional[str]
    user_role: Optional[str]
    metadata_filter: Optional[Dict[str, Any]]

    # Planner output
    tasks: List[SubTask]

    # Accumulator — safe for parallel fan-out via operator.add reducer
    retrieved_chunks: Annotated[List[RetrievedChunk], operator.add]
    task_results: Annotated[List[str], operator.add]

    # Generation
    answer: str

    # Evaluation / retry
    ragas_scores: Optional[RAGASScores]
    retry_count: int
    reformulated_query: Optional[str]