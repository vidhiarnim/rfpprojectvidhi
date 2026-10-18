"""Agentic RFP Evaluation and Supplier Ranking.

Package layout (one module per agent / tool in the brief):

* ``database``          - SQLite persistence (criteria, runs, supplier results)
* ``document_tool``     - Document Tool: PDF -> clean text
* ``evaluation_agent``  - Evaluation Agent: prompt + LLM call (JSON scorecard)
* ``validation_tool``   - Validation Tool: schema checks and normalisation
* ``ranking_tool``      - Ranking Tool: deterministic scoring, benchmarks, PPI, tie-breaks
* ``orchestrator``      - Orchestrator Agent: runs the ten-step workflow
"""

__version__ = "1.0.0"
