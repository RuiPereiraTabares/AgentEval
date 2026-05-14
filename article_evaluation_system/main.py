"""
Main entry point for the Agentic Insight Engine.

Processes customer support cases from CSV files and evaluates
whether cited Microsoft articles adequately address the issues.
"""

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Generator

from . import ArticleEvaluator
from .config.settings import Settings


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _join(items: list, sep: str = '; ') -> str:
    """Join list items as strings, safely handling non-str elements (e.g. dicts from LLM)."""
    return sep.join(str(item) for item in items)


def read_csv_cases(
    filepath: str,
    limit: int = None,
    skip: int = 0
) -> Generator[dict, None, None]:
    """
    Read cases from CSV file.

    Args:
        filepath: Path to CSV file
        limit: Maximum number of cases to read
        skip: Number of cases to skip

    Yields:
        Dictionary for each case
    """
    try:
        f = open(filepath, 'r', encoding='utf-8-sig')
        # Test if we can read the file with UTF-8
        f.read()
        f.seek(0)
    except UnicodeDecodeError:
        f = open(filepath, 'r', encoding='cp1252')
    with f:
        reader = csv.DictReader(f)
        count = 0
        skipped = 0

        for row in reader:
            if skipped < skip:
                skipped += 1
                continue

            if limit and count >= limit:
                break

            yield {
                'case_number': row.get('Case Number', '') or row.get('CaseNumber', ''),
                'title': row.get('Title_mwai', '') or row.get('Title', ''),
                'issue_description': row.get('IssueDescription', ''),
                'language': row.get('Language', 'en-US'),
                'email_type': row.get('EmailType', ''),
                'contains_citations': row.get('ContainsCitations', '').upper() == 'TRUE',
                'urls': [u.strip() for u in row.get('Urls', '').split(',') if u.strip()],
                'ungrounded_percentage': float(row.get('UngroundedPercentage', 0) or 0),
                'error_type': row.get('ErrorType', ''),
                'datetime': row.get('DateTime', ''),
                'sap_product_name': row.get('SapProductName', ''),
                'sap_product_family': row.get('SapProductFamily', ''),
                'sap_path': row.get('SapPath_mwai', '') or row.get('SapPath', '') or row.get('SapPath1', ''),
                'sap_name': row.get('SapName', ''),
            }
            count += 1


def read_mweaeval_csv_cases(
    filepath: str,
    limit: int = None,
    skip: int = 0
) -> Generator[dict, None, None]:
    """
    Read cases from mweaeval CSV file format.

    Expected columns: AiResponse (with [N] markers), Citations (JSON array of URLs),
    plus standard columns like Case Number, Title_mwai, IssueDescription, etc.

    Args:
        filepath: Path to CSV file
        limit: Maximum number of cases to read
        skip: Number of cases to skip

    Yields:
        Dictionary for each case with ai_response and citation_urls keys
    """
    try:
        f = open(filepath, 'r', encoding='utf-8-sig')
        f.read()
        f.seek(0)
    except UnicodeDecodeError:
        f = open(filepath, 'r', encoding='cp1252')
    with f:
        reader = csv.DictReader(f)
        count = 0
        skipped = 0

        for row in reader:
            if skipped < skip:
                skipped += 1
                continue

            if limit and count >= limit:
                break

            # Parse Citations column as JSON array
            citations_raw = row.get('Citations', '[]')
            try:
                citation_urls = json.loads(citations_raw) if citations_raw.strip() else []
            except (json.JSONDecodeError, TypeError):
                citation_urls = []

            yield {
                'case_number': row.get('Case Number', '') or row.get('CaseNumber', ''),
                'title': row.get('Title_mwai', '') or row.get('Title', ''),
                'issue_description': row.get('IssueDescription', ''),
                'ai_response': row.get('AiResponse', ''),
                'citation_urls': citation_urls if isinstance(citation_urls, list) else [],
                'language': row.get('Language', 'en-US'),
                'sap_product_name': row.get('SapProductName', ''),
                'sap_product_family': row.get('SapProductFamily', ''),
                'sap_path': row.get('SapPath_mwai', '') or row.get('SapPath', '') or row.get('SapPath1', ''),
                'sap_name': row.get('SapName', ''),
            }
            count += 1


def _max_citations(results: list[dict]) -> int:
    """Find the maximum number of per-citation results across all cases."""
    mx = 0
    for r in results:
        pcr = r.get('evaluation', {}).get('citation_quality', {}).get('per_citation_results', [])
        mx = max(mx, len(pcr))
    return mx


def _flatten_per_citation(pcr_list: list[dict], max_citations: int) -> dict:
    """Flatten per-citation results into numbered columns.

    Produces: citation_1_url, citation_1_score, citation_1_verdict, citation_1_coverage,
              citation_1_reasoning, citation_2_url, ...
    """
    flat = {}
    for idx in range(max_citations):
        p = f'citation_{idx + 1}_'
        if idx < len(pcr_list):
            pcr = pcr_list[idx]
            flat[f'{p}url'] = pcr.get('url', '')
            flat[f'{p}score'] = pcr.get('support_score', 0)
            flat[f'{p}verdict'] = pcr.get('verdict', '')
            flat[f'{p}coverage'] = pcr.get('coverage_percentage', 0)
            flat[f'{p}reasoning'] = pcr.get('support_reasoning', '')
        else:
            flat[f'{p}url'] = ''
            flat[f'{p}score'] = ''
            flat[f'{p}verdict'] = ''
            flat[f'{p}coverage'] = ''
            flat[f'{p}reasoning'] = ''
    return flat


def write_results_csv(results: list[dict], output_path: str):
    """Write evaluation results to CSV file."""
    if not results:
        logger.warning("No results to write")
        return

    max_cit = _max_citations(results)

    # Flatten results for CSV
    flat_results = []
    for r in results:
        eval_data = r.get('evaluation', {})
        article_eval = eval_data.get('current_article_evaluation', {})
        rel = article_eval.get('relevance', {})
        comp = article_eval.get('completeness', {})
        val = article_eval.get('validity', {})
        dq = eval_data.get('description_quality', {})
        cq = eval_data.get('citation_quality', {})
        rq = eval_data.get('response_quality', {})

        flat = {
            'case_number': r.get('case_number', ''),
            'ai_response': r.get('ai_response', ''),
            'issue_description': eval_data.get('issue_summary', {}).get('raw_description', ''),
            'issue_product': r.get('sap_path', '').split('/')[0].strip() if r.get('sap_path') else '',
            'sap_path': r.get('sap_path', ''),
            'area_path': eval_data.get('issue_summary', {}).get('area_path', ''),
            'area_path_confidence': eval_data.get('issue_summary', {}).get('area_path_confidence', ''),
            'issue_type': eval_data.get('issue_summary', {}).get('issue_type', ''),
            'primary_article_url': article_eval.get('url', ''),
            'primary_article_score': eval_data.get('overall_score', 0),
            'primary_article_verdict': eval_data.get('verdict', ''),
            'primary_article_action_required': eval_data.get('action_required', ''),
            # Relevance details (primary article)
            'article_relevance_score': rel.get('relevance_score', 0),
            'article_relevance_verdict': rel.get('relevance_verdict', ''),
            'article_relevance_matched_aspects': _join(rel.get('matched_aspects', [])),
            'article_relevance_unmatched_aspects': _join(rel.get('unmatched_aspects', [])),
            'article_relevance_product_match': rel.get('product_match', ''),
            'article_relevance_version_match': rel.get('version_match', ''),
            'article_relevance_is_outdated': rel.get('is_outdated', ''),
            # Completeness details (primary article)
            'article_completeness_score': comp.get('completeness_score', 0),
            'article_completeness_verdict': comp.get('completeness_verdict', ''),
            'article_completeness_missing_elements': _join(comp.get('missing_elements', [])),
            'article_completeness_has_prerequisites': comp.get('has_prerequisites', ''),
            'article_completeness_has_step_by_step': comp.get('has_step_by_step', ''),
            'article_completeness_has_examples': comp.get('has_examples', ''),
            'article_completeness_has_troubleshooting': comp.get('has_troubleshooting', ''),
            'article_completeness_has_success_criteria': comp.get('has_success_criteria', ''),
            # Validity details (primary article)
            'article_validity_score': val.get('validity_score', 0),
            'article_validity_verdict': val.get('validity_verdict', ''),
            'article_validity_potential_issues': _join(val.get('potential_issues', [])),
            'article_validity_addresses_root_cause': val.get('addresses_root_cause', ''),
            'article_validity_is_current_solution': val.get('is_current_solution', ''),
            'article_validity_environment_compatible': val.get('environment_compatible', ''),
            'article_validity_confidence_level': val.get('confidence_level', ''),
            # Description quality (support-readiness framework)
            'dq_description_quality_score': dq.get('description_quality_score', 0),
            'dq_description_quality_verdict': dq.get('description_quality_verdict', ''),
            'product_clarity_score': dq.get('product_clarity_score', 0),
            'symptom_specificity_score': dq.get('symptom_specificity_score', 0),
            'operational_context_score': dq.get('operational_context_score', 0),
            'product_clarity_analysis': dq.get('product_clarity_analysis', ''),
            'symptom_specificity_analysis': dq.get('symptom_specificity_analysis', ''),
            'operational_context_analysis': dq.get('operational_context_analysis', ''),
            'dq_missing_elements': _join(dq.get('missing_elements', [])),
            'dq_improvement_suggestions': _join(dq.get('improvement_suggestions', [])),
            'dq_evaluation_reliability_warning': eval_data.get('evaluation_reliability_warning', False),
            # Citation quality — summary
            'citation_grounding_score': cq.get('overall_grounding_score', ''),
            'citation_grounding_verdict': cq.get('overall_verdict', ''),
            'cited_percentage': cq.get('cited_percentage', ''),
            'uncited_percentage': cq.get('uncited_percentage', ''),
            'citations_total': cq.get('citations_total', ''),
            'citations_good': cq.get('citations_good', ''),
            'citations_partial': cq.get('citations_partial', ''),
            'citations_bad': cq.get('citations_bad', ''),
        }
        # Citation quality — per-citation breakdown
        flat.update(_flatten_per_citation(cq.get('per_citation_results', []), max_cit))
        flat.update({
            # Response quality (multi-dimensional)
            'rq_ai_response_quality_score': rq.get('ai_response_quality_score', ''),
            'rq_ai_response_quality_verdict': rq.get('ai_response_quality_verdict', ''),
            'rq_response_quality_score': rq.get('response_quality_score', ''),
            'rq_response_quality_analysis': rq.get('response_quality_analysis', ''),
            'rq_groundedness_score': rq.get('groundedness_score', ''),
            'rq_groundedness_analysis': rq.get('groundedness_analysis', ''),
            'rq_issue_resolution_score': rq.get('issue_resolution_score', ''),
            'rq_issue_resolution_analysis': rq.get('issue_resolution_analysis', ''),
            'rq_quality_weaknesses': _join(rq.get('quality_weaknesses', [])),
            'rq_improvement_suggestions': _join(rq.get('improvement_suggestions', [])),
            # LLM-synthesized recommendation
            'synthesis_priority': eval_data.get('synthesis_priority', ''),
            'synthesis_priority_reason': eval_data.get('synthesis_priority_reason', ''),
            'synthesis_pm_actions': _join(eval_data.get('synthesis_pm_actions', [])),
            'synthesis_root_cause_category': eval_data.get('synthesis_root_cause_category', ''),
            # Summary
            'final_recommendation': eval_data.get('final_recommendation', ''),
            'processing_time_ms': r.get('processing_time_ms', 0),
            'error': r.get('error', '')
        })
        flat_results.append(flat)

    # Collect all fieldnames in stable order
    fieldnames = list(flat_results[0].keys()) if flat_results else []

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_results)

    logger.info(f"Results written to {output_path}")


def write_results_csv_summary(results: list[dict], output_path: str):
    """Write a reduced summary CSV with key scores and reasons only."""
    if not results:
        logger.warning("No results to write")
        return

    flat_results = []
    for r in results:
        eval_data = r.get('evaluation', {})
        article_eval = eval_data.get('current_article_evaluation', {})
        rel = article_eval.get('relevance', {})
        comp = article_eval.get('completeness', {})
        val = article_eval.get('validity', {})
        dq = eval_data.get('description_quality', {})
        cq = eval_data.get('citation_quality', {})
        rq = eval_data.get('response_quality', {})

        flat = {
            'case_number': r.get('case_number', ''),
            'ai_response': r.get('ai_response', ''),
            'issue_description': eval_data.get('issue_summary', {}).get('raw_description', ''),
            'issue_product': r.get('sap_path', '').split('/')[0].strip() if r.get('sap_path') else '',
            'sap_path': r.get('sap_path', ''),
            'area_path': eval_data.get('issue_summary', {}).get('area_path', ''),
            'area_path_confidence': eval_data.get('issue_summary', {}).get('area_path_confidence', ''),
            'primary_article_score': eval_data.get('overall_score', 0),
            'primary_article_verdict': eval_data.get('verdict', ''),
            # Relevance — score + reasons (primary article)
            'article_relevance_score': rel.get('relevance_score', 0),
            'article_relevance_verdict': rel.get('relevance_verdict', ''),
            'article_relevance_matched': _join(rel.get('matched_aspects', [])),
            'article_relevance_unmatched': _join(rel.get('unmatched_aspects', [])),
            # Completeness — score + reasons (primary article)
            'article_completeness_score': comp.get('completeness_score', 0),
            'article_completeness_verdict': comp.get('completeness_verdict', ''),
            'article_completeness_missing': _join(comp.get('missing_elements', [])),
            # Validity — score + reasons (primary article)
            'article_validity_score': val.get('validity_score', 0),
            'article_validity_verdict': val.get('validity_verdict', ''),
            'article_validity_issues': _join(val.get('potential_issues', [])),
            # Description quality — score + reasons (support-readiness framework)
            'dq_description_quality_score': dq.get('description_quality_score', 0),
            'dq_description_quality_verdict': dq.get('description_quality_verdict', ''),
            'product_clarity_score': dq.get('product_clarity_score', 0),
            'symptom_specificity_score': dq.get('symptom_specificity_score', 0),
            'operational_context_score': dq.get('operational_context_score', 0),
            'dq_missing_elements': _join(dq.get('missing_elements', [])),
            'dq_improvement_suggestions': _join(dq.get('improvement_suggestions', [])),
            # Citation quality — summary
            'citation_grounding_score': cq.get('overall_grounding_score', ''),
            'citation_grounding_verdict': cq.get('overall_verdict', ''),
            'cited_percentage': cq.get('cited_percentage', ''),
            'uncited_percentage': cq.get('uncited_percentage', ''),
            'citations_total': cq.get('citations_total', ''),
            'citations_good': cq.get('citations_good', ''),
            'citations_partial': cq.get('citations_partial', ''),
            'citations_bad': cq.get('citations_bad', ''),
        }
        # Citation quality — per-citation breakdown
        max_cit = _max_citations(results)
        flat.update(_flatten_per_citation(cq.get('per_citation_results', []), max_cit))
        flat.update({
            # Response quality (multi-dimensional)
            'rq_ai_response_quality_score': rq.get('ai_response_quality_score', ''),
            'rq_ai_response_quality_verdict': rq.get('ai_response_quality_verdict', ''),
            'rq_response_quality_score': rq.get('response_quality_score', ''),
            'rq_groundedness_score': rq.get('groundedness_score', ''),
            'rq_issue_resolution_score': rq.get('issue_resolution_score', ''),
            'rq_quality_weaknesses': _join(rq.get('quality_weaknesses', [])),
            # LLM-synthesized recommendation
            'synthesis_priority': eval_data.get('synthesis_priority', ''),
            'synthesis_priority_reason': eval_data.get('synthesis_priority_reason', ''),
            'synthesis_pm_actions': _join(eval_data.get('synthesis_pm_actions', [])),
            'synthesis_root_cause_category': eval_data.get('synthesis_root_cause_category', ''),
            # Final
            'final_recommendation': eval_data.get('final_recommendation', ''),
            'error': r.get('error', ''),
        })
        flat_results.append(flat)

    # Collect all fieldnames in stable order
    fieldnames = list(flat_results[0].keys()) if flat_results else []

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_results)

    logger.info(f"Summary results written to {output_path}")


def write_citation_overlaps_csv(overlaps: list[dict], output_path: str):
    """Write citation overlap analysis to a CSV file.

    Args:
        overlaps: List of CitationOverlap dicts.
        output_path: Path to output CSV file.
    """
    if not overlaps:
        logger.warning("No citation overlaps to write")
        return

    fieldnames = [
        "url", "overlap_type", "case_count", "case_numbers",
        "similarity_score", "flag_reason", "recommendation", "issue_snippets",
    ]
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for o in overlaps:
            writer.writerow({
                "url": o.get("url", ""),
                "overlap_type": o.get("overlap_type", ""),
                "case_count": o.get("case_count", 0),
                "case_numbers": "; ".join(o.get("case_numbers", [])),
                "similarity_score": o.get("similarity_score", 0.0),
                "flag_reason": o.get("flag_reason", ""),
                "recommendation": o.get("recommendation", ""),
                "issue_snippets": " | ".join(o.get("issue_snippets", [])),
            })
    logger.info(f"Citation overlaps written to {output_path}")


def write_trend_report_csv(clusters: list[dict], output_path: str):
    """Write trend clusters to a CSV file.

    Args:
        clusters: List of TrendCluster dicts.
        output_path: Path to output CSV file.
    """
    if not clusters:
        logger.warning("No trend clusters to write")
        return

    fieldnames = [
        "cluster_name", "area_path", "priority", "case_count", "case_numbers",
        "root_cause_pattern", "products_affected", "unified_pm_action",
        "estimated_impact", "supporting_evidence",
    ]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for cluster in clusters:
            writer.writerow({
                "cluster_name": cluster.get("cluster_name", ""),
                "area_path": cluster.get("area_path", ""),
                "priority": cluster.get("priority", ""),
                "case_count": cluster.get("case_count", 0),
                "case_numbers": "; ".join(cluster.get("case_numbers", [])),
                "root_cause_pattern": cluster.get("root_cause_pattern", ""),
                "products_affected": "; ".join(cluster.get("products_affected", [])),
                "unified_pm_action": cluster.get("unified_pm_action", ""),
                "estimated_impact": cluster.get("estimated_impact", ""),
                "supporting_evidence": "; ".join(cluster.get("supporting_evidence", [])),
            })

    logger.info(f"Trend report written to {output_path}")


def read_results_csv_as_results(filepath: str) -> list[dict]:
    """Read a flat evaluation output CSV and reconstruct the nested results structure
    expected by TrendSynthesizer.synthesize_trends().

    Compatible with both write_results_csv (detailed) and write_results_csv_summary outputs.

    Args:
        filepath: Path to an existing evaluation output CSV.

    Returns:
        List of result dicts in the same format produced by the evaluation pipeline.
    """
    try:
        f = open(filepath, 'r', encoding='utf-8-sig')
        f.read()
        f.seek(0)
    except UnicodeDecodeError:
        f = open(filepath, 'r', encoding='cp1252')

    results = []
    with f:
        reader = csv.DictReader(f)
        for row in reader:
            # Reconstruct per-citation URL list from citation_N_url columns
            per_citation_results = []
            for idx in range(1, 30):
                url = row.get(f'citation_{idx}_url', '')
                if not url:
                    break
                per_citation_results.append({'url': url})

            result = {
                'case_number': row.get('case_number', ''),
                'ai_response': row.get('ai_response', ''),
                'sap_path': row.get('sap_path', ''),
                'evaluation': {
                    'issue_summary': {
                        'product': row.get('issue_product', ''),
                        'area_path': row.get('area_path', ''),
                        'raw_description': row.get('issue_description', ''),
                        'error_codes': [],
                    },
                    'current_article_evaluation': {
                        'url': row.get('primary_article_url', ''),
                        'title': row.get('primary_article_url', ''),
                    },
                    'content_gaps': {
                        'documentation_gaps': [],
                    },
                    'synthesis_pm_actions': [
                        a.strip()
                        for a in row.get('synthesis_pm_actions', '').split(';')
                        if a.strip()
                    ],
                    'synthesis_root_cause_category': row.get('synthesis_root_cause_category', ''),
                    'synthesis_priority': row.get('synthesis_priority', ''),
                    'verdict': row.get('primary_article_verdict', ''),
                    'overall_score': int(row.get('primary_article_score', 0) or 0),
                    'citation_quality': {
                        'per_citation_results': per_citation_results,
                    },
                },
            }
            results.append(result)

    logger.info(f"Loaded {len(results)} results from {filepath}")
    return results


def write_results_json(results: list[dict], output_path: str):
    """Write evaluation results to JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"Results written to {output_path}")


def process_cases(
    evaluator: ArticleEvaluator,
    cases: list[dict],
    verbose: bool = False
) -> list[dict]:
    """
    Process multiple cases through the evaluator.

    Args:
        evaluator: ArticleEvaluator instance
        cases: List of case dictionaries
        verbose: Whether to print verbose output

    Returns:
        List of results
    """
    results = []
    total = len(cases)

    for i, case in enumerate(cases, 1):
        logger.info(f"Processing case {i}/{total}: {case['case_number']}")

        start_time = datetime.now()

        try:
            # Build issue description from title and description
            full_issue = f"{case['title']}\n\n{case['issue_description']}"

            # Get URLs to evaluate — skip URLs if ContainsCitations is false
            has_citation = case.get('contains_citations', False)
            urls = case.get('urls', []) if has_citation else []

            if not has_citation:
                logger.info(f"  No citation found for case {case['case_number']} — triggering search agent")

            if urls:
                evaluation = evaluator.evaluate(
                    customer_issue=full_issue,
                    recommended_article=urls[0] if len(urls) == 1 else None,
                    case_number=case['case_number'],
                )
                # Handle multiple URLs if needed
                if len(urls) > 1:
                    evaluation['additional_urls'] = urls[1:]
            else:
                evaluation = evaluator.evaluate(
                    customer_issue=full_issue,
                    recommended_article=None,
                    case_number=case['case_number'],
                )

            processing_time = (datetime.now() - start_time).total_seconds() * 1000

            result = {
                'case_number': case['case_number'],
                'sap_path': case.get('sap_path', ''),
                'evaluation': evaluation,
                'processing_time_ms': round(processing_time),
                'error': None
            }

            if verbose:
                logger.info(f"  Score: {evaluation.get('overall_score', 0)}/100")
                logger.info(f"  Verdict: {evaluation.get('verdict', 'unknown')}")

        except Exception as e:
            logger.error(f"Error processing case {case['case_number']}: {e}")
            result = {
                'case_number': case['case_number'],
                'sap_path': case.get('sap_path', ''),
                'evaluation': {},
                'processing_time_ms': 0,
                'error': str(e)
            }

        results.append(result)

    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Evaluate Microsoft support articles for customer issues'
    )
    parser.add_argument(
        'input_file',
        help='Path to input CSV file with customer cases'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output file path (default: evaluation_results.json)',
        default='evaluation_results.json'
    )
    parser.add_argument(
        '--format',
        choices=['json', 'csv'],
        default='json',
        help='Output format (default: json)'
    )
    parser.add_argument(
        '-n', '--limit',
        type=int,
        help='Maximum number of cases to process'
    )
    parser.add_argument(
        '--skip',
        type=int,
        default=0,
        help='Number of cases to skip'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--model',
        default='gpt-4o',
        help='Model to use (default: gpt-4o)'
    )
    parser.add_argument(
        '--token',
        help='MWAI bearer token override (skips MSAL authentication)'
    )
    parser.add_argument(
        '--new-token',
        action='store_true',
        help='Clear MSAL token cache and force interactive re-authentication'
    )

    args = parser.parse_args()

    # Validate input file
    if not os.path.exists(args.input_file):
        logger.error(f"Input file not found: {args.input_file}")
        sys.exit(1)

    # Resolve MWAI token
    from .utils.mwai_client import resolve_mwai_token
    mwai_token = resolve_mwai_token(
        token=getattr(args, 'token', None),
        force_new=getattr(args, 'new_token', False)
    )

    # Initialize evaluator
    logger.info("Initializing Article Evaluator...")
    evaluator = ArticleEvaluator(
        model=args.model,
        mwai_token=mwai_token,
        mwai_token_is_explicit=bool(getattr(args, 'token', None)),
    )

    # Read cases
    logger.info(f"Reading cases from {args.input_file}...")
    cases = list(read_csv_cases(args.input_file, limit=args.limit, skip=args.skip))
    logger.info(f"Loaded {len(cases)} cases")

    if not cases:
        logger.warning("No cases to process")
        sys.exit(0)

    # Process cases
    logger.info("Starting evaluation...")
    results = process_cases(evaluator, cases, verbose=args.verbose)

    # Write output
    if args.format == 'json':
        write_results_json(results, args.output)
    else:
        write_results_csv(results, args.output)

    # Summary
    successful = sum(1 for r in results if not r.get('error'))
    adequate = sum(
        1 for r in results
        if r.get('evaluation', {}).get('verdict') == 'adequate'
    )

    logger.info(f"\n=== Summary ===")
    logger.info(f"Total cases: {len(results)}")
    logger.info(f"Successful evaluations: {successful}")
    logger.info(f"Adequate articles: {adequate}")
    logger.info(f"Results written to: {args.output}")


if __name__ == '__main__':
    main()
