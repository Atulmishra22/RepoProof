from typing import List, Literal
from pydantic import BaseModel, Field

class ExtractedFact(BaseModel):
    category: Literal[
        "technology_used",
        "architecture_pattern",
        "complexity_metric",
        "contribution",
        "performance_optimization",
        "security_hardening",
        "cost_saving"
    ] = Field(
        ...,
        description="The classification of the extracted engineering fact."
    )
    claim: str = Field(
        ...,
        description=(
            "A strong, technical, impact-driven resume bullet point written in "
            "active voice (e.g., 'Implemented dynamic connection pooling to reduce DB latency...'). "
            "It must focus on engineering action and measurable/describable outcome."
        )
    )
    source_file: str = Field(
        ...,
        description="The relative file path inside the repository containing the evidence for this fact."
    )
    snippet: str = Field(
        ...,
        description="The exact block or line of code from the source file that serves as evidence."
    )
    ats_impact: str = Field(
        ...,
        description=(
            "A concise explanation of how this fact demonstrates senior-level expertise "
            "(e.g., scalability, fault tolerance, thread safety, data integrity, decoupling) "
            "optimized for parsing by ATS engines and technical interviewers."
        )
    )

class FactExtractionResult(BaseModel):
    facts: List[ExtractedFact] = Field(
        ...,
        description="A list of validated technical facts extracted from the repository."
    )
    suggested_questions: List[str] = Field(
        ...,
        description=(
            "Follow-up, context-seeking questions to ask the developer. These should prompt "
            "the developer to expand on the rationale, design trade-offs, or production metrics "
            "of the code patterns identified (e.g., 'We saw you used Celery for async background "
            "processing. How did this impact web server responsiveness under high load?')."
        )
    )
