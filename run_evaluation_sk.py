#!/usr/bin/env python
"""
Semantic Kernel runner for the Article Evaluation System.

Supports OpenAI, Azure OpenAI, and Anthropic/Claude via Semantic Kernel.

Usage:
    # OpenAI
    python run_evaluation_sk.py --provider openai --api-key sk-... -n 1

    # Azure OpenAI
    python run_evaluation_sk.py --provider azure \
        --azure-endpoint https://your-resource.openai.azure.com \
        --azure-deployment gpt-4 \
        --api-key your-azure-key \
        -n 1

    # Anthropic/Claude
    python run_evaluation_sk.py --provider anthropic \
        --model claude-sonnet-4-20250514 \
        --api-key your-anthropic-key \
        -n 1

    # Process all cases
    python run_evaluation_sk.py --provider openai --all
"""

import os
import sys
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Check if Semantic Kernel is available
try:
    from article_evaluation_system.sk import SemanticKernelEvaluator
    SK_AVAILABLE = True
except ImportError as e:
    SK_AVAILABLE = False
    SK_IMPORT_ERROR = str(e)

from article_evaluation_system.main import read_csv_cases, write_results_json, write_results_csv


def main():
    parser = argparse.ArgumentParser(
        description='Run Article Evaluation System with Semantic Kernel',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # OpenAI (default)
  python run_evaluation_sk.py --api-key sk-... -n 5

  # Azure OpenAI
  python run_evaluation_sk.py --provider azure \\
      --azure-endpoint https://your-resource.openai.azure.com \\
      --azure-deployment gpt-4 \\
      --api-key your-azure-key -n 5

  # Anthropic/Claude
  python run_evaluation_sk.py --provider anthropic \\
      --model claude-sonnet-4-20250514 \\
      --api-key your-anthropic-key -n 5

  # Use environment variables
  set OPENAI_API_KEY=sk-...
  python run_evaluation_sk.py -n 5

  set ANTHROPIC_API_KEY=your-key
  python run_evaluation_sk.py --provider anthropic -n 5
        """
    )

    # Input/Output options
    parser.add_argument('--input', '-i', default='Article.csv', help='Input CSV file')
    parser.add_argument('--output', '-o', help='Output file (auto-generated if not specified)')
    parser.add_argument('--limit', '-n', type=int, default=5, help='Number of cases to process (default: 5)')
    parser.add_argument('--all', action='store_true', help='Process all cases')
    parser.add_argument('--case', help='Process specific case number')
    parser.add_argument('--skip', type=int, default=0, help='Skip first N cases')
    parser.add_argument('--format', choices=['json', 'csv'], default='json', help='Output format')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    # Provider Configuration
    parser.add_argument('--provider', choices=['openai', 'azure', 'anthropic'], default='openai',
                        help='API provider (default: openai)')
    parser.add_argument('--api-key', help='API key (OpenAI, Azure, or Anthropic)')

    # OpenAI/Anthropic Configuration
    parser.add_argument('--model', default='gpt-4o',
                        help='Model to use (default: gpt-4o for OpenAI, claude-sonnet-4-20250514 for Anthropic)')

    # Azure OpenAI Configuration
    parser.add_argument('--azure-endpoint', help='Azure OpenAI endpoint URL')
    parser.add_argument('--azure-deployment', help='Azure OpenAI deployment name')
    parser.add_argument('--azure-api-version', default='2024-02-15-preview',
                        help='Azure OpenAI API version')

    args = parser.parse_args()

    # Check if SK is available
    if not SK_AVAILABLE:
        print("ERROR: Semantic Kernel is not available.")
        print(f"Import error: {SK_IMPORT_ERROR}")
        print("\nInstall with: pip install semantic-kernel>=1.0.0")
        sys.exit(1)

    # Validate and get API key
    if args.provider == 'openai':
        api_key = args.api_key or os.environ.get('OPENAI_API_KEY')
        env_var = 'OPENAI_API_KEY'
    elif args.provider == 'anthropic':
        api_key = args.api_key or os.environ.get('ANTHROPIC_API_KEY')
        env_var = 'ANTHROPIC_API_KEY'
        # Default model to Claude if using default gpt-4o
        if args.model == 'gpt-4o':
            args.model = 'claude-sonnet-4-20250514'
    else:  # azure
        api_key = args.api_key or os.environ.get('AZURE_OPENAI_API_KEY')
        env_var = 'AZURE_OPENAI_API_KEY'

        # Validate Azure-specific requirements
        if not args.azure_endpoint:
            args.azure_endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT')
        if not args.azure_deployment:
            args.azure_deployment = os.environ.get('AZURE_OPENAI_DEPLOYMENT')

        if not args.azure_endpoint:
            print("ERROR: Azure endpoint required.")
            print("Set --azure-endpoint or AZURE_OPENAI_ENDPOINT environment variable")
            sys.exit(1)
        if not args.azure_deployment:
            print("ERROR: Azure deployment required.")
            print("Set --azure-deployment or AZURE_OPENAI_DEPLOYMENT environment variable")
            sys.exit(1)

    if not api_key:
        print(f"ERROR: No API key provided.")
        print(f"Set {env_var} environment variable or use --api-key")
        sys.exit(1)

    # Check input file
    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    # Determine output file
    if args.output:
        output_file = args.output
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'evaluation_results_sk_{timestamp}.{args.format}'

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

    if args.provider == 'azure':
        print(f"Using Azure OpenAI: {args.azure_endpoint}")
        print(f"Deployment: {args.azure_deployment}")
    elif args.provider == 'anthropic':
        print(f"Using Anthropic/Claude model: {args.model}")
    else:
        print(f"Using OpenAI model: {args.model}")

    if not cases:
        print("No cases to process")
        sys.exit(0)

    # Initialize Semantic Kernel evaluator
    print("Initializing Semantic Kernel evaluator...")
    try:
        if args.provider == 'azure':
            evaluator = SemanticKernelEvaluator(
                api_key=api_key,
                provider='azure',
                azure_endpoint=args.azure_endpoint,
                azure_deployment=args.azure_deployment,
                azure_api_version=args.azure_api_version
            )
        elif args.provider == 'anthropic':
            evaluator = SemanticKernelEvaluator(
                api_key=api_key,
                model=args.model,
                provider='anthropic'
            )
        else:
            evaluator = SemanticKernelEvaluator(
                api_key=api_key,
                model=args.model,
                provider='openai'
            )
        print("Evaluator initialized successfully")
    except Exception as e:
        print(f"ERROR: Failed to initialize evaluator: {e}")
        sys.exit(1)

    # Process cases
    results = []
    for i, case in enumerate(cases, 1):
        print(f"\n[{i}/{len(cases)}] Processing case: {case['case_number']}")
        print(f"  Title: {case['title'][:60]}...")

        start = datetime.now()

        try:
            full_issue = f"{case['title']}\n\n{case['issue_description']}"
            urls = case.get('urls', [])

            product_info = None
            if case.get('sap_product_name') or case.get('sap_name'):
                product_info = {
                    'sap_product_name': case.get('sap_product_name', ''),
                    'sap_product_family': case.get('sap_product_family', ''),
                    'sap_path': case.get('sap_path', ''),
                    'sap_name': case.get('sap_name', ''),
                }

            evaluation = evaluator.evaluate(
                customer_issue=full_issue,
                recommended_article=urls[0] if urls else None,
                product_info=product_info,
            )

            elapsed = (datetime.now() - start).total_seconds()

            result = {
                'case_number': case['case_number'],
                'evaluation': evaluation,
                'processing_time_seconds': round(elapsed, 2),
                'error': None,
                'provider': args.provider
            }

            print(f"  Score: {evaluation.get('overall_score', 0)}/100")
            print(f"  Verdict: {evaluation.get('verdict', 'unknown')}")
            print(f"  Time: {elapsed:.1f}s")

            if args.verbose:
                print(f"  Recommendation: {evaluation.get('final_recommendation', '')[:100]}...")

        except Exception as e:
            print(f"  ERROR: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            result = {
                'case_number': case['case_number'],
                'evaluation': {},
                'processing_time_seconds': 0,
                'error': str(e),
                'provider': args.provider
            }

        results.append(result)

    # Write results
    print(f"\nWriting results to {output_file}...")
    if args.format == 'json':
        write_results_json(results, output_file)
    else:
        write_results_csv(results, output_file)

    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY (Semantic Kernel)")
    print("=" * 50)
    successful = sum(1 for r in results if not r.get('error'))
    adequate = sum(1 for r in results if r.get('evaluation', {}).get('verdict') == 'adequate')
    needs_supp = sum(1 for r in results if r.get('evaluation', {}).get('verdict') == 'needs_supplementation')
    inadequate = sum(1 for r in results if r.get('evaluation', {}).get('verdict') == 'inadequate')
    no_citation = sum(1 for r in results if r.get('evaluation', {}).get('verdict') == 'no_citation_provided')

    print(f"Provider: {args.provider}")
    if args.provider == 'azure':
        print(f"Endpoint: {args.azure_endpoint}")
        print(f"Deployment: {args.azure_deployment}")
    elif args.provider == 'anthropic':
        print(f"Model: {args.model} (Claude)")
    else:
        print(f"Model: {args.model}")

    print(f"\nTotal cases processed: {len(results)}")
    print(f"Successful evaluations: {successful}")
    print(f"  - Adequate: {adequate}")
    print(f"  - Needs supplementation: {needs_supp}")
    print(f"  - Inadequate: {inadequate}")
    print(f"  - No citation provided: {no_citation}")
    print(f"\nResults saved to: {output_file}")


if __name__ == '__main__':
    main()
