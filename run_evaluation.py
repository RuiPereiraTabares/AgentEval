#!/usr/bin/env python
"""
Simple runner script for the Article Evaluation System.

Usage:
    python run_evaluation.py                    # Process first 50 cases
    python run_evaluation.py --all              # Process all cases
    python run_evaluation.py -n 10              # Process first 10 cases
    python run_evaluation.py --case 2508270010003948  # Process specific case
    python run_evaluation.py --token eyJ0eX...  # explicit MWAI token
    python run_evaluation.py --new-token        # force re-prompt for token
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from article_evaluation_system import ArticleEvaluator
from article_evaluation_system.main import read_csv_cases, write_results_json, write_results_csv, write_results_csv_summary


def main():
    parser = argparse.ArgumentParser(description='Run Article Evaluation System')
    parser.add_argument('--input', '-i', default='merged_output.csv', help='Input CSV file')
    parser.add_argument('--output', '-o', help='Output file (auto-generated if not specified)')
    parser.add_argument('--limit', '-n', type=int, default=50, help='Number of cases to process (default: 50)')
    parser.add_argument('--all', action='store_true', help='Process all cases')
    parser.add_argument('--case', help='Process specific case number')
    parser.add_argument('--skip', type=int, default=0, help='Skip first N cases')
    parser.add_argument('--format', choices=['json', 'csv'], default='json', help='Output format')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output (shows per-agent scores and verdict reasoning)')
    parser.add_argument('--debug', action='store_true',
                        help='Debug output (shows raw LLM prompts, responses, and API details)')

    # API Configuration
    parser.add_argument('--model', default='gpt-4o', help='Model to use (default: gpt-4o)')
    parser.add_argument('--token', help='MWAI bearer token. If not provided, will use cached token or prompt interactively.')
    parser.add_argument('--new-token', action='store_true', help='Force re-prompt for a new MWAI token (ignore cache)')

    args = parser.parse_args()

    # Configure logging based on verbosity
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%H:%M:%S'
        )
    elif args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%H:%M:%S'
        )
    else:
        logging.basicConfig(level=logging.WARNING)

    # Resolve MWAI token
    from article_evaluation_system.utils.mwai_client import resolve_mwai_token
    mwai_token = resolve_mwai_token(
        token=args.token,
        force_new=args.new_token
    )

    # Check input file
    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    # Determine output file(s)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if args.output:
        output_file = args.output
    else:
        output_file = f'evaluation_results_{timestamp}.{args.format}'
    # Summary CSV always sits alongside the main output
    output_summary = f'evaluation_summary_{timestamp}.csv'

    # Read cases
    print(f"Reading cases from {args.input}...")
    limit = None if args.all else args.limit
    cases = list(read_csv_cases(args.input, limit=limit, skip=args.skip))

    # Filter for specific case if requested
    if args.case:
        cases = [c for c in cases if c['case_number'] == args.case]
        if not cases:
            print(f"ERROR: Case {args.case} not found")
            sys.exit(1)

    print(f"Loaded {len(cases)} cases to process")
    print(f"Using provider: mwai, model: {args.model}")

    if not cases:
        print("No cases to process")
        sys.exit(0)

    # Initialize evaluator
    print("Initializing evaluator...")
    evaluator = ArticleEvaluator(
        model=args.model,
        provider='mwai',
        mwai_token=mwai_token
    )

    # Process cases
    results = []
    for i, case in enumerate(cases, 1):
        print(f"\n[{i}/{len(cases)}] Processing case: {case['case_number']}")
        print(f"  Title: {case['title'][:60]}...")

        start = datetime.now()

        try:
            full_issue = f"{case['title']}\n\n{case['issue_description']}"
            has_citation = case.get('contains_citations', False)
            urls = case.get('urls', []) if has_citation else []

            if not has_citation:
                print(f"  No citation found — kicking search agent")

            product_info = None
            if case.get('sap_product_name') or case.get('sap_name'):
                product_info = {
                    'sap_product_name': case.get('sap_product_name', ''),
                    'sap_product_family': case.get('sap_product_family', ''),
                    'sap_path': case.get('sap_path', ''),
                    'sap_name': case.get('sap_name', ''),
                }

            transfer_metadata = {
                'transferred': case.get('transferred'),
                'sr_status': case.get('sr_status', ''),
                'reopened': case.get('reopened'),
            }

            evaluation = evaluator.evaluate(
                customer_issue=full_issue,
                recommended_article=urls[0] if urls else None,
                product_info=product_info,
                transfer_metadata=transfer_metadata,
            )

            elapsed = (datetime.now() - start).total_seconds()

            result = {
                'case_number': case['case_number'],
                'evaluation': evaluation,
                'processing_time_seconds': round(elapsed, 2),
                'error': None
            }

            print(f"  Score: {evaluation.get('overall_score', 0)}/100")
            print(f"  Verdict: {evaluation.get('verdict', 'unknown')}")
            print(f"  Time: {elapsed:.1f}s")

            if args.verbose or args.debug:
                # Show description quality (KT framework)
                dq = evaluation.get('description_quality', {})
                if dq:
                    print(f"  --- Description Quality (KT) ---")
                    print(f"  Overall:   {dq.get('description_quality_score', '?'):>3}/100  "
                          f"({dq.get('description_quality_verdict', '?')})")
                    print(f"    Identity (WHAT):    {dq.get('identity_score', '?'):>3}/100  "
                          f"- {dq.get('identity_analysis', '')[:80]}")
                    print(f"    Location (WHERE):   {dq.get('location_score', '?'):>3}/100  "
                          f"- {dq.get('location_analysis', '')[:80]}")
                    print(f"    Timing (WHEN):      {dq.get('timing_score', '?'):>3}/100  "
                          f"- {dq.get('timing_analysis', '')[:80]}")
                    print(f"    Magnitude (EXTENT): {dq.get('magnitude_score', '?'):>3}/100  "
                          f"- {dq.get('magnitude_analysis', '')[:80]}")
                    if dq.get('missing_kt_elements'):
                        print(f"    Missing: {', '.join(dq['missing_kt_elements'][:4])}")
                if evaluation.get('evaluation_reliability_warning'):
                    print(f"  *** LOW CONFIDENCE: description quality below reliability threshold ***")

                # Show per-agent score breakdown
                article_eval = evaluation.get('current_article_evaluation', {})
                rel = article_eval.get('relevance', {})
                comp = article_eval.get('completeness', {})
                val = article_eval.get('validity', {})

                print(f"  --- Agent Score Breakdown ---")
                print(f"  Relevance:    {rel.get('relevance_score', '?'):>3}/100  "
                      f"({rel.get('relevance_verdict', '?')})  "
                      f"product_match={rel.get('product_match', '?')}  "
                      f"version_match={rel.get('version_match', '?')}  "
                      f"outdated={rel.get('is_outdated', '?')}")
                if rel.get('matched_aspects'):
                    print(f"    Matched: {', '.join(rel['matched_aspects'][:5])}")
                if rel.get('unmatched_aspects'):
                    print(f"    Unmatched: {', '.join(rel['unmatched_aspects'][:5])}")

                print(f"  Completeness: {comp.get('completeness_score', '?'):>3}/100  "
                      f"({comp.get('completeness_verdict', '?')})  "
                      f"prereqs={comp.get('has_prerequisites', '?')}  "
                      f"steps={comp.get('has_step_by_step', '?')}  "
                      f"examples={comp.get('has_examples', '?')}  "
                      f"troubleshooting={comp.get('has_troubleshooting', '?')}")
                if comp.get('missing_elements'):
                    print(f"    Missing: {', '.join(comp['missing_elements'][:3])}")

                print(f"  Validity:     {val.get('validity_score', '?'):>3}/100  "
                      f"({val.get('validity_verdict', '?')})  "
                      f"root_cause={val.get('addresses_root_cause', '?')}  "
                      f"current={val.get('is_current_solution', '?')}  "
                      f"env_ok={val.get('environment_compatible', '?')}  "
                      f"confidence={val.get('confidence_level', '?')}")
                if val.get('potential_issues'):
                    print(f"    Issues: {', '.join(val['potential_issues'][:3])}")

                print(f"  --- Verdict Logic ---")
                overall = evaluation.get('overall_score', 0)
                rel_verdict = rel.get('relevance_verdict', 'unknown')
                print(f"    overall_score={overall} (threshold=70), "
                      f"relevance_verdict='{rel_verdict}'")
                if overall >= 70 and rel_verdict in ['excellent', 'good']:
                    print(f"    -> ADEQUATE (score>=70 AND relevance is excellent/good)")
                elif overall >= 70:
                    print(f"    -> NEEDS_SUPPLEMENTATION (score>=70 BUT relevance='{rel_verdict}')")
                elif overall >= 50:
                    print(f"    -> NEEDS_SUPPLEMENTATION (50<=score<70)")
                else:
                    print(f"    -> INADEQUATE (score<50)")

                print(f"  Action: {evaluation.get('action_required', '?')}")
                print(f"  Recommendation: {evaluation.get('final_recommendation', '')[:200]}")

                # Show transfer analysis
                ta = evaluation.get('transfer_analysis', {})
                if ta:
                    print(f"  --- Transfer Analysis ---")
                    print(f"  Transfer reason: {ta.get('transfer_reason', '?')}")
                    print(f"  Confidence: {ta.get('confidence', '?')}")
                    print(f"  Transferred: {ta.get('transferred', '?')}  "
                          f"SR Status: {ta.get('sr_status', '?')}  "
                          f"Reopened: {ta.get('reopened', '?')}")
                    if ta.get('contributing_factors'):
                        for factor in ta['contributing_factors'][:4]:
                            print(f"    - {factor}")
                    if ta.get('escalation_signals_detected'):
                        print(f"  Escalation signals: {', '.join(ta['escalation_signals_detected'][:3])}")
                    if ta.get('narrative'):
                        print(f"  Narrative: {ta['narrative'][:200]}")

        except Exception as e:
            print(f"  ERROR: {e}")
            result = {
                'case_number': case['case_number'],
                'evaluation': {},
                'processing_time_seconds': 0,
                'error': str(e)
            }

        results.append(result)

    # Write results — always produce both detailed + summary CSVs
    print(f"\nWriting detailed results to {output_file}...")
    if args.format == 'json':
        write_results_json(results, output_file)
    else:
        write_results_csv(results, output_file)
    print(f"Writing summary CSV to {output_summary}...")
    write_results_csv_summary(results, output_summary)

    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    successful = sum(1 for r in results if not r.get('error'))
    adequate = sum(1 for r in results if r.get('evaluation', {}).get('verdict') == 'adequate')
    needs_supp = sum(1 for r in results if r.get('evaluation', {}).get('verdict') == 'needs_supplementation')
    inadequate = sum(1 for r in results if r.get('evaluation', {}).get('verdict') == 'inadequate')
    no_citation = sum(1 for r in results if r.get('evaluation', {}).get('verdict') == 'no_citation_provided')

    low_confidence = sum(
        1 for r in results
        if r.get('evaluation', {}).get('evaluation_reliability_warning', False)
    )
    dq_scores = [
        r.get('evaluation', {}).get('description_quality', {}).get('description_quality_score', 0)
        for r in results
        if r.get('evaluation', {}).get('description_quality', {}).get('description_quality_score') is not None
    ]
    avg_dq = round(sum(dq_scores) / len(dq_scores)) if dq_scores else 0

    print(f"Total cases processed: {len(results)}")
    print(f"Successful evaluations: {successful}")
    print(f"  - Adequate: {adequate}")
    print(f"  - Needs supplementation: {needs_supp}")
    print(f"  - Inadequate: {inadequate}")
    print(f"  - No citation provided: {no_citation}")
    print(f"Description quality:")
    print(f"  - Average KT score: {avg_dq}/100")
    print(f"  - Low confidence evaluations: {low_confidence}")

    # Transfer reason breakdown
    transfer_reasons = {}
    for r in results:
        reason = r.get('evaluation', {}).get('transfer_analysis', {}).get('transfer_reason', '')
        if reason:
            transfer_reasons[reason] = transfer_reasons.get(reason, 0) + 1
    if transfer_reasons:
        print(f"Transfer reason breakdown:")
        for reason, count in sorted(transfer_reasons.items(), key=lambda x: -x[1]):
            print(f"  - {reason}: {count}")

    print(f"\nResults saved to:")
    print(f"  Detailed: {output_file}")
    print(f"  Summary:  {output_summary}")


if __name__ == '__main__':
    main()
