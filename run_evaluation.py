#!/usr/bin/env python
"""
Simple runner script for the Agentic Insight Engine.

Usage:
    python run_evaluation.py                    # Process first 50 cases
    python run_evaluation.py --all              # Process all cases
    python run_evaluation.py -n 10              # Process first 10 cases
    python run_evaluation.py --case 2508270010003948  # Process specific case
    python run_evaluation.py --token eyJ0eX...  # explicit MWAI token
    python run_evaluation.py --new-token        # force re-prompt for token

Batch mode:
    python run_evaluation.py --batch-size 50 -i merged_output.csv   # Process first 50
    python run_evaluation.py --batch-size 50 --continue -i merged_output.csv  # Next 50
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
from article_evaluation_system.main import (
    read_csv_cases, read_mweaeval_csv_cases,
    write_results_json, write_results_csv, write_results_csv_summary,
)


def main():
    parser = argparse.ArgumentParser(description='Run Agentic Insight Engine')
    parser.add_argument('--input', '-i', default='merged_output.csv', help='Input CSV file')
    parser.add_argument('--output', '-o', help='Output file (auto-generated if not specified)')
    parser.add_argument('--limit', '-n', type=int, default=50, help='Number of cases to process (default: 50)')
    parser.add_argument('--all', action='store_true', help='Process all cases')
    parser.add_argument('--case', help='Process specific case number')
    parser.add_argument('--skip', type=int, default=0, help='Skip first N cases')
    parser.add_argument('--format', choices=['json', 'csv'], default='csv', help='Output format (default: csv)')
    parser.add_argument('--mweaeval', action='store_true',
                        help='Use mweaeval CSV format (AiResponse + Citations columns) for citation quality evaluation')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output (shows per-agent scores and verdict reasoning)')
    parser.add_argument('--debug', action='store_true',
                        help='Debug output (shows raw LLM prompts, responses, and API details)')

    # API Configuration
    parser.add_argument('--model', default='gpt-4o', help='Model to use (default: gpt-4o)')
    parser.add_argument('--token', help='MWAI bearer token. If not provided, will use cached token or prompt interactively.')
    parser.add_argument('--new-token', action='store_true', help='Force re-prompt for a new MWAI token (ignore cache)')

    # Batch mode
    parser.add_argument('--batch-size', type=int, help='Number of cases per batch (enables batch mode)')
    parser.add_argument('--continue', dest='continue_batch', action='store_true',
                        help='Continue from where the last batch left off (requires --batch-size)')

    args = parser.parse_args()

    BATCH_STATE_FILE = '.batch_state.json'

    # Validate batch args
    if args.continue_batch and not args.batch_size:
        parser.error('--continue requires --batch-size')
    if args.batch_size and args.all:
        parser.error('--batch-size and --all are mutually exclusive')

    # Resolve skip/limit for batch mode
    batch_mode = args.batch_size is not None and not args.case
    if batch_mode:
        if args.continue_batch:
            if not os.path.exists(BATCH_STATE_FILE):
                print("ERROR: No batch state file found. Run without --continue first.")
                sys.exit(1)
            with open(BATCH_STATE_FILE, 'r') as f:
                batch_state = json.load(f)
            if os.path.abspath(args.input) != os.path.abspath(batch_state.get('input_file', '')):
                print(f"ERROR: Input file mismatch. State expects '{batch_state['input_file']}', got '{args.input}'")
                sys.exit(1)
            skip = batch_state['last_offset']
            limit = args.batch_size
            print(f"Continuing from case {skip + 1} (batch size: {args.batch_size})")
        else:
            skip = args.skip
            limit = args.batch_size
            print(f"Batch mode: processing cases {skip + 1}-{skip + args.batch_size}")
    else:
        skip = args.skip
        limit = None if args.all else args.limit

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
    if args.mweaeval:
        cases = list(read_mweaeval_csv_cases(args.input, limit=limit, skip=skip))
    else:
        cases = list(read_csv_cases(args.input, limit=limit, skip=skip))

    # Filter for specific case if requested
    if args.case:
        cases = [c for c in cases if c['case_number'] == args.case]
        if not cases:
            print(f"ERROR: Case {args.case} not found")
            sys.exit(1)

    print(f"Loaded {len(cases)} cases to process")
    print(f"Using provider: mwai, model: {args.model}")
    if args.mweaeval:
        print(f"Mode: mweaeval (citation quality evaluation)")

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

            product_info = None
            if case.get('sap_product_name') or case.get('sap_name'):
                product_info = {
                    'sap_product_name': case.get('sap_product_name', ''),
                    'sap_product_family': case.get('sap_product_family', ''),
                    'sap_path': case.get('sap_path', ''),
                    'sap_name': case.get('sap_name', ''),
                }

            if args.mweaeval:
                # Citation quality evaluation mode
                ai_response = case.get('ai_response', '')
                citation_urls = case.get('citation_urls', [])
                print(f"  Citations: {len(citation_urls)} URLs")

                evaluation = evaluator.evaluate_with_citations(
                    customer_issue=full_issue,
                    ai_response=ai_response,
                    citation_urls=citation_urls,
                    product_info=product_info,
                )
            else:
                # Standard evaluation mode
                has_citation = case.get('contains_citations', False)
                urls = case.get('urls', []) if has_citation else []

                if not has_citation:
                    print(f"  No citation found — kicking search agent")

                evaluation = evaluator.evaluate(
                    customer_issue=full_issue,
                    recommended_article=urls[0] if urls else None,
                    product_info=product_info,
                )

            elapsed = (datetime.now() - start).total_seconds()

            result = {
                'case_number': case['case_number'],
                'ai_response': case.get('ai_response', ''),
                'sap_path': case.get('sap_path', ''),
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

                # Show citation quality (mweaeval mode)
                cq = evaluation.get('citation_quality', {})
                if cq and cq.get('citations_total', 0) > 0:
                    print(f"  --- Citation Quality ---")
                    print(f"  Grounding:  {cq.get('overall_grounding_score', '?'):>3}/100  "
                          f"({cq.get('overall_verdict', '?')})")
                    print(f"  Cited: {cq.get('cited_percentage', 0):.1f}%  "
                          f"Uncited: {cq.get('uncited_percentage', 0):.1f}%")
                    print(f"  Citations: {cq.get('citations_total', 0)} total  "
                          f"({cq.get('citations_good', 0)} good, "
                          f"{cq.get('citations_partial', 0)} partial, "
                          f"{cq.get('citations_bad', 0)} bad)")
                    for pcr in cq.get('per_citation_results', []):
                        print(f"    [{pcr.get('citation_index', '?')}] "
                              f"score={pcr.get('support_score', 0):>3}  "
                              f"verdict={pcr.get('verdict', '?'):<8}  "
                              f"coverage={pcr.get('coverage_percentage', 0):.1f}%  "
                              f"url={pcr.get('url', '')[:60]}")
                        if pcr.get('support_reasoning'):
                            print(f"        {pcr['support_reasoning'][:120]}")

                # Show response quality (multi-dimensional)
                rq = evaluation.get('response_quality', {})
                if rq and rq.get('ai_response_quality_score') is not None:
                    print(f"  --- AI Response Quality ---")
                    print(f"  Overall:          {rq.get('ai_response_quality_score', '?'):>3}/100  "
                          f"({rq.get('ai_response_quality_verdict', '?')})")
                    print(f"    Response Quality:  {rq.get('response_quality_score', '?'):>3}/100  "
                          f"- {rq.get('response_quality_analysis', '')[:80]}")
                    print(f"    Groundedness:     {rq.get('groundedness_score', '?'):>3}/100  "
                          f"- {rq.get('groundedness_analysis', '')[:80]}")
                    print(f"    Issue Resolution: {rq.get('issue_resolution_score', '?'):>3}/100  "
                          f"- {rq.get('issue_resolution_analysis', '')[:80]}")
                    if rq.get('quality_weaknesses'):
                        print(f"    Weaknesses: {'; '.join(rq['quality_weaknesses'][:3])}")
                    if rq.get('improvement_suggestions'):
                        print(f"    Suggestions: {'; '.join(rq['improvement_suggestions'][:3])}")

                # Show LLM-synthesized recommendation
                synth_priority = evaluation.get('synthesis_priority', '')
                if synth_priority:
                    print(f"  --- LLM Synthesis ---")
                    print(f"  Priority: {synth_priority.upper()}  "
                          f"({evaluation.get('synthesis_priority_reason', '')})")
                    print(f"  Root cause: {evaluation.get('synthesis_root_cause_category', '')}")
                    pm_actions = evaluation.get('synthesis_pm_actions', [])
                    if pm_actions:
                        print(f"  PM Actions:")
                        for action in pm_actions:
                            print(f"    - {action}")

        except Exception as e:
            print(f"  ERROR: {e}")
            result = {
                'case_number': case['case_number'],
                'ai_response': case.get('ai_response', ''),
                'sap_path': case.get('sap_path', ''),
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

    # Save batch state
    if batch_mode:
        new_offset = skip + len(results)
        prev_total = batch_state.get('cases_processed_total', 0) if args.continue_batch else 0
        state = {
            'input_file': os.path.abspath(args.input),
            'last_offset': new_offset,
            'batch_size': args.batch_size,
            'cases_processed_total': prev_total + len(results),
            'timestamp': datetime.now().isoformat(),
        }
        with open(BATCH_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        print(f"\nBatch complete. {len(results)} cases processed (total: {state['cases_processed_total']}).")
        print(f"Run with --continue to process next {args.batch_size} cases.")

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

    # Synthesis priority distribution
    priority_red = sum(
        1 for r in results
        if r.get('evaluation', {}).get('synthesis_priority', '').lower() == 'red'
    )
    priority_yellow = sum(
        1 for r in results
        if r.get('evaluation', {}).get('synthesis_priority', '').lower() == 'yellow'
    )
    priority_green = sum(
        1 for r in results
        if r.get('evaluation', {}).get('synthesis_priority', '').lower() == 'green'
    )

    print(f"Total cases processed: {len(results)}")
    print(f"Successful evaluations: {successful}")
    print(f"  - Adequate: {adequate}")
    print(f"  - Needs supplementation: {needs_supp}")
    print(f"  - Inadequate: {inadequate}")
    print(f"  - No citation provided: {no_citation}")
    if priority_red or priority_yellow or priority_green:
        print(f"Synthesis priority distribution:")
        print(f"  - RED: {priority_red}  YELLOW: {priority_yellow}  GREEN: {priority_green}")
    print(f"Description quality:")
    print(f"  - Average KT score: {avg_dq}/100")
    print(f"  - Low confidence evaluations: {low_confidence}")

    # Response quality summary (mweaeval mode)
    rq_scores = [
        r.get('evaluation', {}).get('response_quality', {}).get('ai_response_quality_score', 0)
        for r in results
        if r.get('evaluation', {}).get('response_quality', {}).get('ai_response_quality_score') is not None
        and r.get('evaluation', {}).get('response_quality', {}).get('ai_response_quality_score', 0) > 0
    ]
    if rq_scores:
        avg_rq = round(sum(rq_scores) / len(rq_scores))
        print(f"AI Response quality:")
        print(f"  - Average composite score: {avg_rq}/100")

    # Citation quality summary (mweaeval mode)
    cq_scores = [
        r.get('evaluation', {}).get('citation_quality', {}).get('overall_grounding_score', 0)
        for r in results
        if r.get('evaluation', {}).get('citation_quality', {}).get('citations_total', 0) > 0
    ]
    if cq_scores:
        avg_cq = round(sum(cq_scores) / len(cq_scores))
        total_good = sum(
            r.get('evaluation', {}).get('citation_quality', {}).get('citations_good', 0)
            for r in results
        )
        total_partial = sum(
            r.get('evaluation', {}).get('citation_quality', {}).get('citations_partial', 0)
            for r in results
        )
        total_bad = sum(
            r.get('evaluation', {}).get('citation_quality', {}).get('citations_bad', 0)
            for r in results
        )
        print(f"Citation quality:")
        print(f"  - Average grounding score: {avg_cq}/100")
        print(f"  - Citations: {total_good} good, {total_partial} partial, {total_bad} bad")

    print(f"\nResults saved to:")
    print(f"  Detailed: {output_file}")
    print(f"  Summary:  {output_summary}")


if __name__ == '__main__':
    main()
