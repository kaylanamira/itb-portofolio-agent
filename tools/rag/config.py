from dataclasses import dataclass, field

@dataclass
class EmbeddingConfig:
    model_name: str = "intfloat/multilingual-e5-large"
    dimension: int = 1024
    max_length: int = 512
    batch_size: int = 32
    device: str = "cuda"
    normalize_embeddings: bool = True
    query_prefix: str = "query: "
    passage_prefix: str = "passage: "


@dataclass
class ChunkingConfig:
    chunk_size: int = 512 
    chunk_overlap: int = 64
    min_chunk_size: int = 64
    short_text_chunk_size: int = 256
    short_text_overlap: int = 32


@dataclass
class VectorDBConfig:
    porto_table: str = "vector_chunks"
    wisudawan_table: str = "wisudawan_vector_chunks"
    embedding_dimension: int = 1024
    hnsw_m: int = 16
    hnsw_ef_construction: int = 200


@dataclass
class RetrievalConfig:
    top_k_dense: int = 10
    top_k_sparse: int = 10
    top_k_rerank: int = 5 
    rrf_k: int = 60
    relevance_threshold: float = 0.35
    max_retry_attempts: int = 2
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"


@dataclass
class GenerationConfig:
    model_name: str = "qwen2.5:7b"
    max_new_tokens: int = 1024
    temperature: float = 0.1
    top_p: float = 0.9
    repetition_penalty: float = 1.1


@dataclass
class EvaluationConfig:
    min_faithfulness: float = 0.7
    min_context_relevance: float = 0.5
    min_answer_relevance: float = 0.6
    max_retries: int = 2
    judge_model: str = "Qwen/Qwen2.5-7B-Instruct"


@dataclass
class RAGConfig:
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    vector_db: VectorDBConfig = field(default_factory=VectorDBConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)

    postgres_dsn: str = "postgresql://user:password@localhost:5432/itb_db"


DEFAULT_CONFIG = RAGConfig()