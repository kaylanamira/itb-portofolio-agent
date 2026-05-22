from __future__ import annotations

import logging
from typing import List, Optional

from tools.rag.config import GenerationConfig

logger = logging.getLogger(__name__)

_tokenizer = None
_model = None


def _load_model(config: GenerationConfig):
    global _tokenizer, _model
    if _model is not None:
        return
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        import torch

        logger.info(f"Loading LLM: {config.model_name}")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        _tokenizer = AutoTokenizer.from_pretrained(config.model_name)
        _model = AutoModelForCausalLM.from_pretrained(
            config.model_name,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
        )
        _model.eval()
    except ImportError as e:
        raise RuntimeError(
            "Install transformers, bitsandbytes, and torch to use local LLM."
        ) from e


class LLMGenerator:
    def __init__(
        self,
        config: GenerationConfig,
        api_base_url: Optional[str] = None,
        api_key: str = "EMPTY",
    ):
        self.config = config
        self.api_base_url = api_base_url
        self.api_key = api_key
        if api_base_url is None:
            _load_model(config)

    def generate(
        self,
        query: str,
        context_chunks: List[str],
        system_prompt: Optional[str] = None,
        extra_instruction: str = "",
    ) -> str:
        context_text = self._format_context(context_chunks)
        system = system_prompt or self._default_system_prompt()
        user_message = self._build_user_prompt(query, context_text, extra_instruction)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ]

        if self.api_base_url:
            return self._generate_api(messages)
        return self._generate_local(messages)

    def generate_for_evaluation(
        self,
        prompt: str,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        if self.api_base_url:
            return self._generate_api(messages)
        return self._generate_local(messages)

    # ------------------------------------------------------------------ #
    # Prompt helpers                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _default_system_prompt() -> str:
        return (
            "Kamu adalah asisten analitik akademik ITB yang membantu pemangku kepentingan "
            "menganalisis data portofolio dan ulasan wisudawan. "
            "Jawab HANYA berdasarkan konteks yang diberikan. "
            "Jika informasi tidak tersedia dalam konteks, katakan 'Informasi tidak tersedia dalam data yang diambil.' "
            "Jangan menambahkan informasi di luar konteks. "
            "Gunakan bahasa yang sama dengan pertanyaan (Indonesia atau Inggris)."
        )

    @staticmethod
    def _build_user_prompt(query: str, context: str, extra: str) -> str:
        parts = [
            f"KONTEKS YANG DIAMBIL:\n{context}",
            f"\nPERTANYAAN: {query}",
        ]
        if extra:
            parts.append(f"\nINSTRUKSI TAMBAHAN: {extra}")
        parts.append("\nJAWABAN:")
        return "\n".join(parts)

    @staticmethod
    def _format_context(chunks: List[str]) -> str:
        if not chunks:
            return "[Tidak ada konteks yang tersedia]"
        lines = []
        for i, chunk in enumerate(chunks, 1):
            lines.append(f"[{i}] {chunk.strip()}")
        return "\n\n".join(lines)

    def _generate_local(self, messages: list) -> str:
        import torch

        text = _tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        model_inputs = _tokenizer([text], return_tensors="pt").to(_model.device)

        with torch.no_grad():
            generated_ids = _model.generate(
                **model_inputs,
                max_new_tokens=self.config.max_new_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                repetition_penalty=self.config.repetition_penalty,
                do_sample=self.config.temperature > 0,
            )

        new_tokens = generated_ids[0][model_inputs.input_ids.shape[-1]:]
        return _tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    def _generate_api(self, messages: list) -> str:
        import httpx

        payload = {
            "model": self.config.model_name,
            "messages": messages,
            "max_tokens": self.config.max_new_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = httpx.post(
            f"{self.api_base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()