"""
Script to create sample training data for TCFD classifier.
This script avoids importing the full classifier to bypass dependency issues.
"""

import json
import random
from pathlib import Path

# Define TCFD requirements
TCFD_REQUIREMENTS = {
    "Governance": [
        {"id": "G.1", "title": "Board oversight", "description": "Board's oversight of climate-related risks and opportunities"},
        {"id": "G.2", "title": "Management's role", "description": "Management's role in assessing and managing climate-related risks and opportunities"}
    ],
    "Strategy": [
        {"id": "S.1", "title": "Climate-related Risks and Opportunities", "description": "Climate-related risks and opportunities"},
        {"id": "S.2", "title": "Impact on Business", "description": "Impact on business, strategy, and financial planning"},
        {"id": "S.3", "title": "Resilience of Strategy", "description": "Resilience under different climate scenarios"}
    ],
    "Risk Management": [
        {"id": "R.1", "title": "Risk Identification", "description": "Risk identification and assessment"},
        {"id": "R.2", "title": "Risk Management", "description": "Risk management processes"},
        {"id": "R.3", "title": "Integration into Overall Risk Management", "description": "Integration into enterprise risk management"}
    ],
    "Metrics & Targets": [
        {"id": "M.1", "title": "Climate-related Metrics", "description": "Climate-related metrics"},
        {"id": "M.2", "title": "Greenhouse Gas Emissions", "description": "Scope 1, 2, and 3 GHG emissions"},
        {"id": "M.3", "title": "Targets and Performance", "description": "Targets and performance against targets"}
    ]
}

LABEL_OPTIONS = ["Not disclosed", "Partially disclosed", "Disclosed"]

SAMPLE_TEXTS = {
    "Disclosed": [
        "The company has established a comprehensive climate governance framework with clear board oversight and management responsibility for climate-related risks and opportunities.",
        "Our board of directors regularly reviews climate-related risks and opportunities as part of its risk oversight duties. The sustainability committee provides quarterly reports on climate strategy progress.",
        "We have identified several climate-related risks including physical risks from extreme weather events and transition risks from regulatory changes. These are integrated into our enterprise risk management process.",
        "The company has set science-based targets aligned with the Paris Agreement, including a 50% reduction in Scope 1 and 2 emissions by 2030 and net-zero by 2050.",
        "We disclose our Scope 1, 2, and 3 greenhouse gas emissions in accordance with the GHG Protocol. Total Scope 1 emissions were 125,000 tCO2e, Scope 2 were 89,000 tCO2e, and Scope 3 were 450,000 tCO2e in 2023."
    ],
    "Partially disclosed": [
        "Some information about climate governance is mentioned in our annual report, but details on board oversight and specific responsibilities are limited.",
        "We are working on understanding climate-related risks and opportunities. Initial assessments have been conducted but comprehensive analysis is still in progress.",
        "The company has begun setting climate targets. We have committed to reducing emissions but specific metrics and timelines are still being developed.",
        "Partial disclosure of greenhouse gas emissions is provided for Scope 1 and 2, but Scope 3 emissions data is not yet available.",
        "Climate-related risks are mentioned in our risk management framework, but specific methodologies and assessment processes are not fully detailed."
    ],
    "Not disclosed": [
        "The report does not contain any information about climate governance or board oversight of climate-related risks.",
        "No information is provided about climate-related risks and opportunities or their impact on the company's business strategy.",
        "The company has not disclosed any climate-related targets or goals for reducing greenhouse gas emissions.",
        "Greenhouse gas emissions data is not disclosed in this report.",
        "There is no information about the company's approach to managing climate-related risks."
    ]
}

def create_sample_training_data(num_samples: int = 100, output_path: str = "./datasets/tcfd_training_sample.json"):
    """Create synthetic training data for testing."""
    print(f"Creating {num_samples} synthetic training samples...")

    # Get all requirement IDs
    req_ids = []
    for pillar, requirements in TCFD_REQUIREMENTS.items():
        for req in requirements:
            req_ids.append((req["id"], pillar, req["title"], req["description"]))

    training_data = []
    for _ in range(num_samples):
        req_id, pillar, title, description = random.choice(req_ids)
        label = random.choice(LABEL_OPTIONS)

        # Select a sample text
        sample_text = random.choice(SAMPLE_TEXTS[label])

        training_data.append({
            "requirement_id": req_id,
            "pillar": pillar,
            "title": title,
            "description": description,
            "text": sample_text,
            "label": label,
            "relevance_score": random.uniform(0.7, 0.95)
        })

    # Ensure output directory exists
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Save to JSON
    with open(output_path, "w") as f:
        json.dump(training_data, f, indent=2)

    print(f"Saved {len(training_data)} synthetic samples to {output_path}")

    # Print label distribution
    label_counts = {label: 0 for label in LABEL_OPTIONS}
    for item in training_data:
        label_counts[item["label"]] += 1

    print("\nLabel distribution:")
    for label, count in label_counts.items():
        percentage = (count / len(training_data)) * 100
        print(f"  {label}: {count} ({percentage:.1f}%)")

if __name__ == "__main__":
    create_sample_training_data(num_samples=100)
