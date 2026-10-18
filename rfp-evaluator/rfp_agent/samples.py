"""Metadata for the bundled synthetic supplier PDFs (used by the demo button and CLI)."""
from datetime import date
from pathlib import Path

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_rfps"

SAMPLE_SUPPLIERS = [
    {"file": "01_Apex_Systems_Proposal.pdf", "supplier_name": "Apex Systems",
     "submission_date": date(2026, 9, 22), "experience_rating": 4.0},
    {"file": "02_BrightPath_Tech_Proposal.pdf", "supplier_name": "BrightPath Tech",
     "submission_date": date(2026, 9, 25), "experience_rating": 2.0},
    {"file": "03_NexaWorks_Proposal.pdf", "supplier_name": "NexaWorks",
     "submission_date": date(2026, 9, 22), "experience_rating": 4.0},
    {"file": "04_Orbit_Digital_Proposal.pdf", "supplier_name": "Orbit Digital",
     "submission_date": date(2026, 9, 20), "experience_rating": 5.0},
    {"file": "05_Zenith_CloudWorks_Proposal.pdf", "supplier_name": "Zenith CloudWorks",
     "submission_date": date(2026, 9, 25), "experience_rating": 1.0},
]

BY_FILE = {s["file"]: s for s in SAMPLE_SUPPLIERS}
