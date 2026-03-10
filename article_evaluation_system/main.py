"""
Main entry point for the Article Evaluation System.

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

            # Parse transfer metadata (None if column absent from CSV)
            transferred_raw = row.get('Transferred')
            transferred = None
            if transferred_raw is not None and transferred_raw.strip():
                transferred = transferred_raw.strip().upper() == 'TRUE'

            reopened_raw = row.get('Reopened')
            reopened = None
            if reopened_raw is not None and reopened_raw.strip():
                reopened = reopened_raw.strip().upper() == 'TRUE'

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
                'sap_path': row.get('SapPath_mwai', '') or row.get('SapPath', ''),
                'sap_name': row.get('SapName', ''),
                'transferred': transferred,
                'sr_status': row.get('SRStatus', '') or row.get('SR Status', ''),
                'reopened': reopened,
            }
            count += 1


def write_results_csv(results: list[dict], output_path: str):
    """Write evaluation results to CSV file."""
    if not results:
        logger.warning("No results to write")
        return

    # Flatten results for CSV
    flat_results = []
    for r in results:
        eval_data = r.get('evaluation', {})
        article_eval = eval_data.get('current_article_evaluation', {})
        rel = article_eval.get('relevance', {})
        comp = article_eval.get('completeness', {})
        val = article_eval.get('validity', {})
        dq = eval_data.get('description_quality', {})

        flat = {
            'case_number': r.get('case_number', ''),
            'issue_description': eval_data.get('issue_summary', {}).get('raw_description', ''),
            'issue_product': eval_data.get('issue_summary', {}).get('product', ''),
            'issue_type': eval_data.get('issue_summary', {}).get('issue_type', ''),
            'article_url': article_eval.get('url', ''),
            'overall_score': eval_data.get('overall_score', 0),
            'verdict': eval_data.get('verdict', ''),
            'action_required': eval_data.get('action_required', ''),
            # Relevance details
            'relevance_score': rel.get('relevance_score', 0),
            'relevance_verdict': rel.get('relevance_verdict', ''),
            'relevance_matched_aspects': '; '.join(rel.get('matched_aspects', [])),
            'relevance_unmatched_aspects': '; '.join(rel.get('unmatched_aspects', [])),
            'relevance_product_match': rel.get('product_match', ''),
            'relevance_version_match': rel.get('version_match', ''),
            'relevance_is_outdated': rel.get('is_outdated', ''),
            # Completeness details
            'completeness_score': comp.get('completeness_score', 0),
            'completeness_verdict': comp.get('completeness_verdict', ''),
            'completeness_missing_elements': '; '.join(comp.get('missing_elements', [])),
            'completeness_has_prerequisites': comp.get('has_prerequisites', ''),
            'completeness_has_step_by_step': comp.get('has_step_by_step', ''),
            'completeness_has_examples': comp.get('has_examples', ''),
            'completeness_has_troubleshooting': comp.get('has_troubleshooting', ''),
            'completeness_has_success_criteria': comp.get('has_success_criteria', ''),
            # Validity details
            'validity_score': val.get('validity_score', 0),
            'validity_verdict': val.get('validity_verdict', ''),
            'validity_potential_issues': '; '.join(val.get('potential_issues', [])),
            'validity_addresses_root_cause': val.get('addresses_root_cause', ''),
            'validity_is_current_solution': val.get('is_current_solution', ''),
            'validity_environment_compatible': val.get('environment_compatible', ''),
            'validity_confidence_level': val.get('confidence_level', ''),
            # Description quality (KT framework)
            'description_quality_score': dq.get('description_quality_score', 0),
            'description_quality_verdict': dq.get('description_quality_verdict', ''),
            'kt_identity_score': dq.get('identity_score', 0),
            'kt_location_score': dq.get('location_score', 0),
            'kt_timing_score': dq.get('timing_score', 0),
            'kt_magnitude_score': dq.get('magnitude_score', 0),
            'kt_identity_analysis': dq.get('identity_analysis', ''),
            'kt_location_analysis': dq.get('location_analysis', ''),
            'kt_timing_analysis': dq.get('timing_analysis', ''),
            'kt_magnitude_analysis': dq.get('magnitude_analysis', ''),
            'kt_missing_elements': '; '.join(dq.get('missing_kt_elements', [])),
            'kt_improvement_suggestions': '; '.join(dq.get('improvement_suggestions', [])),
            'evaluation_reliability_warning': eval_data.get('evaluation_reliability_warning', False),
            # Transfer analysis
            'transfer_reason': eval_data.get('transfer_analysis', {}).get('transfer_reason', ''),
            'transfer_confidence': eval_data.get('transfer_analysis', {}).get('confidence', ''),
            'transferred': eval_data.get('transfer_analysis', {}).get('transferred', ''),
            'sr_status': eval_data.get('transfer_analysis', {}).get('sr_status', ''),
            'reopened': eval_data.get('transfer_analysis', {}).get('reopened', ''),
            'transfer_contributing_factors': '; '.join(
                eval_data.get('transfer_analysis', {}).get('contributing_factors', [])
            ),
            'transfer_escalation_signals': '; '.join(
                eval_data.get('transfer_analysis', {}).get('escalation_signals_detected', [])
            ),
            'transfer_narrative': eval_data.get('transfer_analysis', {}).get('narrative', ''),
            # Summary
            'final_recommendation': eval_data.get('final_recommendation', ''),
            'processing_time_ms': r.get('processing_time_ms', 0),
            'error': r.get('error', '')
        }
        flat_results.append(flat)

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=flat_results[0].keys())
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
        ta = eval_data.get('transfer_analysis', {})

        flat = {
            'case_number': r.get('case_number', ''),
            'issue_description': eval_data.get('issue_summary', {}).get('raw_description', ''),
            'overall_score': eval_data.get('overall_score', 0),
            'verdict': eval_data.get('verdict', ''),
            # Relevance — score + reasons
            'relevance_score': rel.get('relevance_score', 0),
            'relevance_verdict': rel.get('relevance_verdict', ''),
            'relevance_matched': '; '.join(rel.get('matched_aspects', [])),
            'relevance_unmatched': '; '.join(rel.get('unmatched_aspects', [])),
            # Completeness — score + reasons
            'completeness_score': comp.get('completeness_score', 0),
            'completeness_verdict': comp.get('completeness_verdict', ''),
            'completeness_missing': '; '.join(comp.get('missing_elements', [])),
            # Validity — score + reasons
            'validity_score': val.get('validity_score', 0),
            'validity_verdict': val.get('validity_verdict', ''),
            'validity_issues': '; '.join(val.get('potential_issues', [])),
            # Description quality — score + reasons
            'description_quality_score': dq.get('description_quality_score', 0),
            'description_quality_verdict': dq.get('description_quality_verdict', ''),
            'description_missing': '; '.join(dq.get('missing_kt_elements', [])),
            'description_improvements': '; '.join(dq.get('improvement_suggestions', [])),
            # Transfer
            'transfer_reason': ta.get('transfer_reason', ''),
            'transfer_narrative': ta.get('narrative', ''),
            # Final
            'final_recommendation': eval_data.get('final_recommendation', ''),
            'error': r.get('error', ''),
        }
        flat_results.append(flat)

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=flat_results[0].keys())
        writer.writeheader()
        writer.writerows(flat_results)

    logger.info(f"Summary results written to {output_path}")


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

            # Build transfer metadata from CSV columns
            transfer_metadata = {
                'transferred': case.get('transferred'),
                'sr_status': case.get('sr_status', ''),
                'reopened': case.get('reopened'),
            }

            if urls:
                evaluation = evaluator.evaluate(
                    customer_issue=full_issue,
                    recommended_article=urls[0] if len(urls) == 1 else None,
                    transfer_metadata=transfer_metadata,
                )
                # Handle multiple URLs if needed
                if len(urls) > 1:
                    evaluation['additional_urls'] = urls[1:]
            else:
                evaluation = evaluator.evaluate(
                    customer_issue=full_issue,
                    recommended_article=None,
                    transfer_metadata=transfer_metadata,
                )

            processing_time = (datetime.now() - start_time).total_seconds() * 1000

            result = {
                'case_number': case['case_number'],
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
        '--api-key',
        help='Anthropic API key (or set ANTHROPIC_API_KEY env var)'
    )
    parser.add_argument(
        '--model',
        default='claude-sonnet-4-20250514',
        help='Claude model to use'
    )

    args = parser.parse_args()

    # Validate input file
    if not os.path.exists(args.input_file):
        logger.error(f"Input file not found: {args.input_file}")
        sys.exit(1)

    # Get API key
    api_key = args.api_key or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        logger.error("No API key provided. Set ANTHROPIC_API_KEY or use --api-key")
        sys.exit(1)

    # Initialize evaluator
    logger.info("Initializing Article Evaluator...")
    evaluator = ArticleEvaluator(api_key=api_key, model=args.model)

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
