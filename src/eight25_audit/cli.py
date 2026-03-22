from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from .ai import AiAnalysisError, run_ai_analysis
from .metrics import extract_metrics
from .prompt_logging import write_prompt_log
from .scrape import fetch_html


def _fmt_list(items, max_items: int = 20, show_all: bool = False) -> str:
    if not items:
        return "(none)"
    if show_all:
        return "; ".join(str(x) for x in items)
    if len(items) <= max_items:
        return "; ".join(str(x) for x in items)
    head = "; ".join(str(x) for x in items[:max_items])
    return f"{head}; ... (+{len(items) - max_items} more)"


def _print_metrics(metrics, *, show_all_scraped: bool = False) -> None:
    print("=== FACTUAL METRICS ===")
    print(f"Total word count: {metrics.word_count}")
    print(
        "Counted words "
        + ("(all): " if show_all_scraped else "(sample): ")
        + _fmt_list(metrics.counted_words, max_items=40, show_all=show_all_scraped)
    )
    print(f"Headings: H1={metrics.headings.h1} H2={metrics.headings.h2} H3={metrics.headings.h3}")
    print(
        "Heading texts: "
        f"H1={_fmt_list(metrics.heading_texts.get('h1', []), 10, show_all_scraped)} | "
        f"H2={_fmt_list(metrics.heading_texts.get('h2', []), 10, show_all_scraped)} | "
        f"H3={_fmt_list(metrics.heading_texts.get('h3', []), 10, show_all_scraped)}"
    )
    print(f"CTAs (buttons + primary action links): {metrics.cta_count}")
    print(
        "Counted CTA texts: "
        + _fmt_list(metrics.counted_cta_texts, max_items=20, show_all=show_all_scraped)
    )
    print(
        "Links: "
        f"internal={metrics.links.internal} external={metrics.links.external} other={metrics.links.other}"
    )
    print(
        "Counted internal links "
        + ("(all): " if show_all_scraped else "(sample): ")
        + _fmt_list(metrics.counted_internal_links, max_items=10, show_all=show_all_scraped)
    )
    print(
        "Counted external links "
        + ("(all): " if show_all_scraped else "(sample): ")
        + _fmt_list(metrics.counted_external_links, max_items=10, show_all=show_all_scraped)
    )
    print(
        "Counted other links "
        + ("(all): " if show_all_scraped else "(sample): ")
        + _fmt_list(metrics.counted_other_links, max_items=10, show_all=show_all_scraped)
    )
    print(
        "Images: "
        f"total={metrics.images.total_images} missing_alt={metrics.images.missing_alt} "
        f"missing_alt_pct={metrics.images.missing_alt_pct}%"
    )
    image_sample = [
        f"src={img.src or ''} alt={img.alt or ''} missing_alt={img.counted_missing_alt}"
        for img in (metrics.counted_images if show_all_scraped else metrics.counted_images[:8])
    ]
    print(
        "Counted images "
        + ("(all): " if show_all_scraped else "(sample): ")
        + _fmt_list(image_sample, max_items=8, show_all=show_all_scraped)
    )
    print(f"Meta title: {metrics.meta_title or ''}")
    print(f"Meta description: {metrics.meta_description or ''}")


def _print_ai(report) -> None:
    print("\n=== AI INSIGHTS ===")
    print(report.summary)

    for bucket in [
        "seo_structure",
        "messaging_clarity",
        "cta_usage",
        "content_depth",
        "ux_structural_concerns",
    ]:
        items = report.insights.get(bucket, [])
        print(f"\n-- {bucket} --")
        if not items:
            print("(none)")
            continue
        for i, item in enumerate(items, start=1):
            ev = "; ".join(item.evidence[:3])
            print(f"{i}. {item.title}")
            if ev:
                print(f"   Evidence: {ev}")
            print(f"   Why: {item.why_it_matters}")

    print("\n=== RECOMMENDATIONS (PRIORITIZED) ===")
    for rec in sorted(report.recommendations, key=lambda r: r.priority):
        print(f"P{rec.priority}: {rec.title}")
        print(f"  Reasoning: {rec.reasoning}")
        if rec.metric_references:
            print("  Metric refs: " + ", ".join(rec.metric_references))
        for a in rec.actions[:4]:
            print(f"  - {a}")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(prog="eight25-audit", description="Single-URL AI website audit")
    parser.add_argument("url", help="URL to audit")
    parser.add_argument("--no-ai", action="store_true", help="Only compute factual metrics")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument(
        "--show-all-scraped",
        action="store_true",
        help="Print full scraped/countable items in terminal output (can be very verbose)",
    )
    parser.add_argument(
        "--strict-ai",
        action="store_true",
        help="Exit non-zero if the AI step fails (default: soft-fail with ai=null + prompt_log)",
    )
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification")
    parser.add_argument(
        "--no-truststore",
        action="store_true",
        help="Do not use OS trust store integration (truststore)",
    )
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    parser.add_argument("--log-dir", default="logs/prompt-logs")

    args = parser.parse_args()

    # On Windows and in corporate environments, certs may only exist in the OS store.
    # truststore lets Python/httpx use the native trust store.
    if not args.no_truststore:
        use_truststore = os.getenv("EIGHT25_USE_TRUSTSTORE", "1") not in {"0", "false", "False"}
        if use_truststore:
            try:
                import truststore  # type: ignore

                truststore.inject_into_ssl()
            except Exception:
                pass

    fetch = fetch_html(args.url, verify_tls=not args.insecure)
    if fetch.blocked_reason:
        blocked_output = {
            "requested_url": fetch.requested_url,
            "final_url": fetch.final_url,
            "status_code": fetch.status_code,
            "fetched_at": fetch.fetched_at.isoformat(),
            "metrics": None,
            "ai": None,
            "ai_error": None,
            "fetch_error": fetch.blocked_reason,
            "prompt_log": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        if args.json:
            print(json.dumps(blocked_output, indent=2))
            return
        raise SystemExit(
            f"Could not scrape page content: {fetch.blocked_reason}. "
            "Try another URL or use a page without bot protection."
        )

    metrics = extract_metrics(fetch.html, page_url=fetch.final_url)

    ai_report = None
    system_prompt = user_prompt = ""
    structured_input = {}
    raw_model_output = ""
    prompt_log = None
    ai_error: str | None = None

    if not args.no_ai:
        if not os.getenv("OPENAI_API_KEY"):
            raise SystemExit(
                "OPENAI_API_KEY is not set. Set it in .env (see .env.example) or pass --no-ai."
            )
        try:
            ai_report, system_prompt, user_prompt, structured_input, raw_model_output = run_ai_analysis(
                url=fetch.final_url, metrics=metrics, model=args.model
            )
            prompt_log = write_prompt_log(
                log_dir=args.log_dir,
                model=args.model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                structured_input=structured_input,
                raw_model_output=raw_model_output,
                parsed_output=ai_report.model_dump(),
                error=None,
            )
        except AiAnalysisError as e:
            prompt_log = write_prompt_log(
                log_dir=args.log_dir,
                model=args.model,
                system_prompt=e.system_prompt,
                user_prompt=e.user_prompt,
                structured_input=e.structured_input,
                raw_model_output=e.raw_model_output,
                parsed_output=None,
                error=str(e),
            )
            ai_error = str(e)
            if args.strict_ai:
                raise

    output = {
        "requested_url": fetch.requested_url,
        "final_url": fetch.final_url,
        "status_code": fetch.status_code,
        "fetched_at": fetch.fetched_at.isoformat(),
        "metrics": metrics.model_dump(mode="json"),
        "ai": ai_report.model_dump(mode="json") if ai_report else None,
        "ai_error": ai_error,
        "fetch_error": None,
        "prompt_log": prompt_log.model_dump(mode="json") if prompt_log else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if args.json:
        print(json.dumps(output, indent=2))
        return

    print(f"URL: {fetch.final_url} (status {fetch.status_code})")
    _print_metrics(metrics, show_all_scraped=args.show_all_scraped)
    if ai_report:
        _print_ai(ai_report)

    if prompt_log:
        print(f"\nPrompt log: {args.log_dir}/{prompt_log.id}.json")


if __name__ == "__main__":
    main()
