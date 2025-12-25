from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from src.config import SETTINGS
from src.schema import (
    FacultyPageExtraction,
    PaperSelection,
    RecruitingInsight,
    ResearchDeps,
    ResearchSynthesis,
    ScholarProfileResult,
)
from src.tools import register_downselector_tools, register_main_agent_tools, register_tools

# Shared provider for all agents
_provider = OpenRouterProvider(api_key=SETTINGS.openrouter_api_key)

faculty_extractor_agent = Agent(
    OpenRouterModel(SETTINGS.faculty_extractor_agent.model, provider=_provider),
    deps_type=ResearchDeps,
    output_type=FacultyPageExtraction,
)


@faculty_extractor_agent.instructions
def faculty_extractor_instructions() -> str:
    return SETTINGS.faculty_extractor_agent.instructions


downselector_agent = Agent(
    OpenRouterModel(SETTINGS.downselector_agent.model, provider=_provider),
    deps_type=ResearchDeps,
    output_type=PaperSelection,
)


@downselector_agent.instructions
def downselector_instructions() -> str:
    return SETTINGS.downselector_agent.instructions


recruiting_agent = Agent(
    OpenRouterModel(SETTINGS.recruiting_agent.model, provider=_provider),
    deps_type=ResearchDeps,
    output_type=RecruitingInsight,
)


@recruiting_agent.instructions
def recruiting_instructions() -> str:
    return SETTINGS.recruiting_agent.instructions


scholar_finder_agent = Agent(
    OpenRouterModel(SETTINGS.scholar_finder_agent.model, provider=_provider),
    deps_type=ResearchDeps,
    output_type=ScholarProfileResult,
)


@scholar_finder_agent.instructions
def scholar_finder_instructions() -> str:
    return SETTINGS.scholar_finder_agent.instructions


# Main orchestrator
main_agent = Agent(
    OpenRouterModel(SETTINGS.main_agent.model, provider=_provider),
    deps_type=ResearchDeps,
    output_type=ResearchSynthesis,
)


@main_agent.instructions
def main_instructions() -> str:
    return SETTINGS.main_agent.instructions


# Register basic research tools (web_search, fetch_url, extract_pdf)
register_tools(main_agent)
register_tools(downselector_agent)
register_tools(faculty_extractor_agent)
register_tools(scholar_finder_agent)
register_tools(recruiting_agent)

# Register main agent specific tools (submit_research_plan)
register_main_agent_tools(main_agent)

# Register downselector-specific tools (fetch_scholar_papers, review_paper_pdf)
register_downselector_tools(downselector_agent)