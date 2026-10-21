"""Opt-in Sol comparison on the same frozen originals, never a live campaign.

Without --execute: offline preflight only. The explicit 1.65 USD proposal
requires separate authorization before --execute; it does not change app limits.
"""
from scripts.run_objective_validation import CONFIG,ROOT,main
from sales.commercial.ai import validate_config

# Verified official contract: Chat Completions without tools, medium reasoning.
# Unknown local tokenizer: preserve conservative UTF-8 bound, never assume Mini's
# encoding. Same frozen evidence, larger accounting envelope only.
SOL_CONFIG=validate_config({
    **CONFIG,'model':'gpt-6.1-sol','max_input_tokens':20480,
    'max_output_tokens':4096,'input_cost_per_million':2.0,
    'output_cost_per_million':10.0,'max_estimated_cost':1.65,
})
SOL_RESULT=ROOT/'implementation-report/commercial-objective/VALIDATION-AI-SOL-01.json'

if __name__=='__main__':
    main(config=SOL_CONFIG,result_path=SOL_RESULT)
