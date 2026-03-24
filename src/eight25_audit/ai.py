from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlparse

from openai import OpenAI

from .models import AiReport, PageMetrics


_METRIC_REF_RE = re.compile(
    r"\b(word_count|headings\.(h1|h2|h3)|cta_count|links\.(internal|external|other)|"
    r"images\.(total_images|missing_alt|missing_alt_pct)|"
    r"missing_alt|missing_alt_pct|meta_(title|description)|"
    r"sample_headings|sample_cta_texts|text_sample)\s*=\s*[^\s,;]+",
    re.I,
)

_METRIC_KEY_ONLY_RE = re.compile(
    r"\b(word_count|headings\.(h1|h2|h3)|cta_count|links\.(internal|external|other)|"
    r"images\.(total_images|missing_alt|missing_alt_pct)|"
    r"missing_alt|missing_alt_pct|meta_(title|description)|"
    r"sample_headings|sample_cta_texts|text_sample)\b",
    re.I,
)

_PLACEHOLDER_REF_RE = re.compile(r"=\s*\.\.\.(?:\s|$)")
_ANGLE_PLACEHOLDER_RE = re.compile(r"<[^>\n]+>")
_LOW_VALUE_TEXT_SAMPLE_RE = re.compile(r"^\s*text_sample\s*=\s*(?:short|long)?\s*excerpt\s*$", re.I)


def _contains_placeholder(text: str) -> bool:
    t = text or ""
    # Treat explicit placeholder refs (e.g. cta_count=...) as invalid.
    if _PLACEHOLDER_REF_RE.search(t):
        return True
    # Treat angle-bracket placeholder snippets (e.g. text_sample=<intro copy>) as invalid.
    if _ANGLE_PLACEHOLDER_RE.search(t):
        return True
    # Reject low-information pseudo evidence labels.
    if _LOW_VALUE_TEXT_SAMPLE_RE.match(t):
        return True
    # Also reject bare placeholder-only tokens.
    return t.strip() == "..."


def _contains_metric_reference(text: str) -> bool:
    t = text or ""
    return bool(_METRIC_REF_RE.search(t) or _METRIC_KEY_ONLY_RE.search(t))


def _validate_grounding(report: AiReport) -> list[str]:
    issues: list[str] = []

    if not (report.summary or "").strip():
        issues.append("summary must be non-empty")

    if len(report.recommendations) < 3 or len(report.recommendations) > 5:
        issues.append("recommendations count must be between 3 and 5")

    for bucket, items in report.insights.items():
        if not items:
            issues.append(f"insights.{bucket} must contain at least one item")
            continue
        for idx, item in enumerate(items, start=1):
            evidence = item.evidence or []
            if not evidence:
                issues.append(f"insights.{bucket}[{idx}] has empty evidence")
                continue
            if any(_contains_placeholder(ev) for ev in evidence):
                issues.append(f"insights.{bucket}[{idx}] contains placeholder evidence")
            if not any(_contains_metric_reference(ev) for ev in evidence):
                issues.append(f"insights.{bucket}[{idx}] missing explicit metric reference")

    for idx, rec in enumerate(report.recommendations, start=1):
        actions = rec.actions or []
        if len(actions) < 2 or len(actions) > 4:
            issues.append(f"recommendations[{idx}] actions count must be between 2 and 4")
        refs = rec.metric_references or []
        if not refs:
            issues.append(f"recommendations[{idx}] has empty metric_references")
            continue
        if any(_contains_placeholder(ref) for ref in refs):
            issues.append(f"recommendations[{idx}] contains placeholder metric reference")
        if not any(_contains_metric_reference(ref) for ref in refs):
            issues.append(f"recommendations[{idx}] missing explicit metric reference")

    return issues


class AiAnalysisError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        system_prompt: str,
        user_prompt: str,
        structured_input: dict[str, Any],
        raw_model_output: str,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.structured_input = structured_input
        self.raw_model_output = raw_model_output
        self.__cause__ = cause


def build_system_prompt() -> str:
    return (
        "You are a senior website audit analyst for a performance-focused web agency. "
        "Your job is to produce precise, high-signal analysis from provided structured data only. "
        "Never invent facts, never infer hidden technical details, and never use vague filler language. "
        "Every insight must include concrete metric references in key=value form and explain business impact. "
        "If data is limited or blocked, explicitly state the limitation and lower confidence in claims. "
        "Recommendations must be prioritized, actionable, and directly traceable to metric evidence. "
        "Output must be a single valid JSON object with no markdown and no extra commentary."
    )


def build_user_prompt(*, url: str, metrics: PageMetrics) -> tuple[str, dict[str, Any]]:
    metrics_for_ai = {
        "word_count": metrics.word_count,
        "headings": metrics.headings.model_dump(),
        "cta_count": metrics.cta_count,
        "links": metrics.links.model_dump(),
        "images": metrics.images.model_dump(),
        "meta_title": metrics.meta_title,
        "meta_description": metrics.meta_description,
        "sample_headings": metrics.sample_headings,
        "sample_cta_texts": metrics.sample_cta_texts,
        "text_sample": metrics.text_sample,
    }

    structured_input: dict[str, Any] = {
        "url": url,
        "metrics": metrics_for_ai,
        "instructions": {
            "grounding_rules": [
                "Reference metrics by key and value, e.g. word_count=523.",
                "Each insight evidence item and each recommendation metric_references list must contain at least one key=value reference.",
                "Allowed keys: word_count, headings.h1, headings.h2, headings.h3, cta_count, links.internal, links.external, links.other, images.total_images, images.missing_alt, images.missing_alt_pct, meta_title, meta_description, sample_headings, sample_cta_texts, text_sample.",
                "Do not use unknown keys (for example: sample_text). Use text_sample instead.",
                "Never use placeholders like key=... or bare ...",
                "Do not give generic advice; tie points to headings/links/images/CTAs/meta.",
                "Avoid claims that require unavailable data (page speed, Core Web Vitals, conversion rate, accessibility score, rankings).",
                "If the page appears blocked/error-like, say this clearly and avoid normal-page optimization assumptions.",
                "Keep recommendations actionable and prioritized (3-5).",
            ],
            "quality_rules": [
                "Use concise, reviewer-friendly language.",
                "Do not repeat the same point across multiple buckets.",
                "Use confidence-calibrated wording: 'suggests' or 'indicates' when evidence is indirect.",
                "Each recommendation should include 2-4 concrete actions.",
                "The insights object must include exactly five buckets: seo_structure, messaging_clarity, cta_usage, content_depth, ux_structural_concerns.",
                "Each insight bucket must contain at least one item.",
            ],
            "output_contract": {
                "insight_buckets": [
                    "seo_structure",
                    "messaging_clarity",
                    "cta_usage",
                    "content_depth",
                    "ux_structural_concerns",
                ],
                "recommendations_count": "3-5",
            },
        },
    }

    output_template = {
        "summary": "<string>",
        "insights": {
            "seo_structure": [
                {
                    "title": "<string>",
                    "evidence": ["word_count=123"],
                    "why_it_matters": "<string>",
                }
            ],
            "messaging_clarity": [
                {
                    "title": "<string>",
                    "evidence": ["meta_title=example title"],
                    "why_it_matters": "<string>",
                }
            ],
            "cta_usage": [
                {
                    "title": "<string>",
                    "evidence": ["cta_count=2"],
                    "why_it_matters": "<string>",
                }
            ],
            "content_depth": [
                {
                    "title": "<string>",
                    "evidence": ["headings.h2=3"],
                    "why_it_matters": "<string>",
                }
            ],
            "ux_structural_concerns": [
                {
                    "title": "<string>",
                    "evidence": ["images.missing_alt=1"],
                    "why_it_matters": "<string>",
                }
            ],
        },
        "recommendations": [
            {
                "priority": 1,
                "title": "<string>",
                "reasoning": "<string>",
                "actions": ["<string>", "<string>", "<string>"],
                "metric_references": ["word_count=123", "headings.h2=3"],
            }
        ],
    }

    user_prompt = (
        "Analyze this single web page and produce structured insights and recommendations.\n\n"
        "Use ONLY the structured input below; do not invent facts.\n\n"
        "Reliability requirements:\n"
        "- Return strict JSON only (no markdown, no preface text).\n"
        "- Use only allowed metric keys exactly as listed.\n"
        "- Keep insights specific and avoid generic best-practice filler.\n"
        "- Ground each claim in provided metrics or text_sample evidence.\n"
        "- If evidence is limited or indicates an error/blocked page, explicitly state that limitation.\n\n"
        "- If using text_sample evidence, quote an actual phrase from text_sample; do not use labels like text_sample=short excerpt.\n\n"
        "- Do not copy wording from OUTPUT_TEMPLATE_JSON; it is structural guidance only.\n\n"
        "Output completeness checklist (mandatory):\n"
        "- insights must include all 5 required buckets exactly once.\n"
        "- each insights bucket must include at least 1 item.\n"
        "- recommendations must include 3 to 5 items sorted by priority (1 is highest).\n"
        "- prefer 4-5 recommendations when multiple distinct issues exist; use 3 only when evidence is limited.\n"
        "- each recommendation must include 2 to 4 actions and non-empty metric_references.\n\n"
        "Output MUST be a single JSON object (not an array) matching this template shape. "
        "Do not wrap in markdown. Do not add commentary.\n\n"
        f"OUTPUT_TEMPLATE_JSON:\n{json.dumps(output_template, indent=2)}\n\n"
        f"STRUCTURED_INPUT_JSON:\n{json.dumps(structured_input, indent=2)}\n"
    )

    return user_prompt, structured_input


def _json_schema() -> dict[str, Any]:
    # JSON Schema kept explicit (no $ref) for LLM reliability.
    insight_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "why_it_matters": {"type": "string"},
        },
        "required": ["title", "evidence", "why_it_matters"],
    }

    recommendation = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "priority": {"type": "integer", "minimum": 1, "maximum": 5},
            "title": {"type": "string"},
            "reasoning": {"type": "string"},
            "actions": {"type": "array", "items": {"type": "string"}},
            "metric_references": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["priority", "title", "reasoning", "actions", "metric_references"],
    }

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "insights": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "seo_structure": {"type": "array", "items": insight_item},
                    "messaging_clarity": {"type": "array", "items": insight_item},
                    "cta_usage": {"type": "array", "items": insight_item},
                    "content_depth": {"type": "array", "items": insight_item},
                    "ux_structural_concerns": {"type": "array", "items": insight_item},
                },
                "required": [
                    "seo_structure",
                    "messaging_clarity",
                    "cta_usage",
                    "content_depth",
                    "ux_structural_concerns",
                ],
            },
            "recommendations": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": recommendation,
            },
        },
        "required": ["summary", "insights", "recommendations"],
    }


def run_ai_analysis(
    *, url: str, metrics: PageMetrics, model: str
) -> tuple[AiReport, str, str, dict[str, Any], str]:
    system_prompt = build_system_prompt()
    user_prompt, structured_input = build_user_prompt(url=url, metrics=metrics)

    base_url_env = os.getenv("OPENAI_BASE_URL")
    base_url = (base_url_env or "").strip()
    if base_url:
        parsed_url = urlparse(base_url)
        if not parsed_url.scheme:
            base_url = "https://" + base_url
        client = OpenAI(base_url=base_url)
    else:
        client = OpenAI()

    # Many OpenAI-compatible gateways (e.g., OpenRouter) do not consistently support
    # Chat Completions `response_format` / `json_schema`. We only rely on it for the
    # official OpenAI API base URL.
    effective_base_url = base_url or "https://api.openai.com/v1"
    supports_response_format = "api.openai.com" in effective_base_url

    def _chat_text(*, prompt: str, response_format: dict[str, Any] | None) -> str:
        kwargs: dict[str, Any] = {}
        if response_format is not None and supports_response_format:
            kwargs["response_format"] = response_format

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            **kwargs,
        )
        content = resp.choices[0].message.content
        return content or ""

    def _try_parse_json_object(text: str) -> dict[str, Any] | None:
        if not text:
            return None
        try:
            parsed_any = json.loads(text)
        except Exception:
            # Best-effort extract first JSON object from mixed output
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                parsed_any = json.loads(text[start : end + 1])
            except Exception:
                return None

        if isinstance(parsed_any, dict):
            return parsed_any
        if isinstance(parsed_any, list) and len(parsed_any) == 1 and isinstance(parsed_any[0], dict):
            return parsed_any[0]
        return None

    attempt1_text = ""
    attempt2_text = ""

    # Attempt 1
    try:
        attempt1_text = _chat_text(
            prompt=user_prompt,
            response_format=(
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "audit_report",
                        "schema": _json_schema(),
                        "strict": True,
                    },
                }
                if supports_response_format
                else None
            ),
        )
    except Exception as e:  # noqa: BLE001
        attempt1_text = f"<<CALL_ERROR>> {type(e).__name__}({repr(str(e))})"

    parsed1 = _try_parse_json_object(attempt1_text)
    grounding_issues_1: list[str] = []
    if parsed1 is not None:
        try:
            report = AiReport.model_validate(parsed1)
            grounding_issues_1 = _validate_grounding(report)
            if not grounding_issues_1:
                return report, system_prompt, user_prompt, structured_input, attempt1_text
        except Exception:
            pass

    # Attempt 2 (repair): include the invalid output so the model can correct itself.
    repair_prefix = ""
    if grounding_issues_1:
        repair_prefix = (
            "Your previous output failed grounding checks. Fix all issues exactly.\n"
            + "\n".join(f"- {issue}" for issue in grounding_issues_1)
            + "\n\n"
        )

    repair_user = (
        "You MUST return a single JSON object matching the required schema. "
        "Your previous output was invalid. Fix it.\n\n"
        + repair_prefix
        +
        "Previous output:\n"
        + attempt1_text
        + "\n\n"
        + user_prompt
    )

    try:
        attempt2_text = _chat_text(
            prompt=repair_user,
            response_format=({"type": "json_object"} if supports_response_format else None),
        )
    except Exception as e:  # noqa: BLE001
        attempt2_text = f"<<CALL_ERROR>> {type(e).__name__}({repr(str(e))})"

    parsed2 = _try_parse_json_object(attempt2_text)
    if parsed2 is None:
        raise AiAnalysisError(
            "AI response could not be parsed as a JSON object",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            structured_input=structured_input,
            raw_model_output=f"<<ATTEMPT1>>\n{attempt1_text}\n<<ATTEMPT2>>\n{attempt2_text}",
        )

    try:
        report = AiReport.model_validate(parsed2)
        grounding_issues_2 = _validate_grounding(report)
        if grounding_issues_2:
            raise AiAnalysisError(
                "AI output did not satisfy grounding constraints",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                structured_input=structured_input,
                raw_model_output=(
                    f"<<ATTEMPT1>>\n{attempt1_text}\n<<ATTEMPT2>>\n{attempt2_text}"
                    f"\n<<GROUNDING_ISSUES>>\n" + "\n".join(grounding_issues_2)
                ),
            )
    except AiAnalysisError:
        raise
    except Exception as e:  # noqa: BLE001
        raise AiAnalysisError(
            "AI output did not match expected schema",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            structured_input=structured_input,
            raw_model_output=f"<<ATTEMPT1>>\n{attempt1_text}\n<<ATTEMPT2>>\n{attempt2_text}",
            cause=e,
        ) from e

    return report, system_prompt, user_prompt, structured_input, attempt2_text
