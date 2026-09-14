from app.agents.base import SpecialistAgent

SECURITY_AGENT = SpecialistAgent(
    name="security",
    category="security",
    focus=(
        "hardcoded secrets, injection, authentication or authorization gaps, unsafe "
        "deserialization, insecure cryptography, dangerous file or command handling, "
        "and dependency-related security risk visible in the change"
    ),
)
