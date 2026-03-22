from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import PromptLog


def ensure_dir(path: str | os.PathLike[str]) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_prompt_log(
    *,
    log_dir: str | os.PathLike[str],
    model: str,
    system_prompt: str,
    user_prompt: str,
    structured_input: dict[str, Any],
    raw_model_output: str,
    parsed_output: dict[str, Any] | None,
    error: str | None = None,
) -> PromptLog:
    log_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    created_at = datetime.now(timezone.utc)

    prompt_log = PromptLog(
        id=log_id,
        created_at=created_at,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        structured_input=structured_input,
        raw_model_output=raw_model_output,
        parsed_output=parsed_output,
        error=error,
    )

    out_dir = ensure_dir(log_dir)
    out_path = out_dir / f"{log_id}.json"
    out_path.write_text(prompt_log.model_dump_json(indent=2), encoding="utf-8")
    return prompt_log
