import json
import operator
from typing import Annotated, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from loguru import logger
from typing_extensions import TypedDict

from open_notebook.ai.provision import provision_langchain_model
from open_notebook.domain.notebook import vector_search
from open_notebook.domain.research import ResearchMission
from open_notebook.exceptions import OpenNotebookError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.text_utils import extract_text_content


class ResearchState(TypedDict):
    mission_id: str
    query: str
    notebook_id: Optional[str]
    depth: str  # quick, comprehensive, exhaustive
    model_override: Optional[str]
    plan: Optional[dict]  # Research plan with sections
    notes: Annotated[list, operator.add]  # Accumulated research notes
    reflections: Optional[list]  # Reflection insights
    report: Optional[str]  # Final written report
    summary: Optional[str]
    status: str
    progress: int
    error: Optional[str]
    execution_log: Annotated[list, operator.add]  # Agent activity log


DEPTH_SECTION_LIMITS = {
    "quick": (3, 4),
    "comprehensive": (4, 6),
    "exhaustive": (5, 7),
}

DEPTH_SEARCH_RESULTS = {
    "quick": 5,
    "comprehensive": 10,
    "exhaustive": 15,
}


async def _update_mission(mission_id: str, **kwargs) -> None:
    """Load a ResearchMission by ID and update its fields."""
    mission = await ResearchMission.get(mission_id)
    if not mission:
        logger.warning(f"ResearchMission {mission_id} not found for update")
        return
    for key, value in kwargs.items():
        setattr(mission, key, value)
    await mission.save()


async def _log_to_mission(
    mission_id: str, phase: str, agent: str, message: str, details=None
) -> None:
    """Append a log entry to the mission's execution log."""
    mission = await ResearchMission.get(mission_id)
    if mission:
        await mission.add_log_entry(phase, agent, message, details)


async def planning_node(state: ResearchState, config: RunnableConfig) -> dict:
    """Create a structured research plan from the query."""
    try:
        mission_id = state["mission_id"]
        query = state["query"]
        depth = state.get("depth", "comprehensive")
        min_sections, max_sections = DEPTH_SECTION_LIMITS.get(depth, (4, 6))

        await _update_mission(mission_id, status="planning", progress=5)

        system_prompt = f"""You are a research planning agent. Analyze the following research query and create a structured research plan.

Your plan should contain between {min_sections} and {max_sections} sections, each representing a distinct aspect of the research topic.

For each section, provide:
- "title": A clear, concise title for the section
- "description": A 1-2 sentence description of what this section should cover
- "research_strategy": One of "search_sources" (search existing notebook sources), "web_search" (search the web - will fall back to source search if unavailable), or "synthesize" (combine findings from other sections, no new research needed)

At least half of the sections should use "search_sources" or "web_search" strategy. At most one section should use "synthesize", typically the conclusion or summary section.

Output ONLY valid JSON in this exact format:
{{
  "title": "Overall research title",
  "objective": "One sentence describing the research goal",
  "sections": [
    {{
      "title": "Section Title",
      "description": "What this section covers",
      "research_strategy": "search_sources"
    }}
  ]
}}"""

        model = await provision_langchain_model(
            system_prompt,
            config.get("configurable", {}).get("model_id") or state.get("model_override"),
            "chat",
            max_tokens=2000,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Research query: {query}"),
        ]

        ai_message = await model.ainvoke(messages)
        content = extract_text_content(ai_message.content)
        cleaned = clean_thinking_content(content)

        # Parse JSON from response, handling possible markdown fencing
        json_str = cleaned.strip()
        if json_str.startswith("```"):
            json_str = json_str.split("\n", 1)[1] if "\n" in json_str else json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            elif "```" in json_str:
                json_str = json_str[: json_str.rfind("```")]
            json_str = json_str.strip()

        plan = json.loads(json_str)

        await _update_mission(mission_id, status="planning", progress=10, plan=plan)
        await _log_to_mission(
            mission_id,
            "planning",
            "planner",
            f"Created research plan with {len(plan.get('sections', []))} sections",
            {"plan_title": plan.get("title", "")},
        )

        logger.info(
            f"Research plan created for mission {mission_id}: "
            f"{len(plan.get('sections', []))} sections"
        )

        return {
            "plan": plan,
            "status": "planning",
            "progress": 10,
            "execution_log": [
                {
                    "phase": "planning",
                    "agent": "planner",
                    "message": f"Created plan with {len(plan.get('sections', []))} sections",
                }
            ],
        }

    except OpenNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        await _update_mission(
            state["mission_id"],
            status="failed",
            error_message=str(user_message),
        )
        raise error_class(user_message) from e


async def research_node(state: ResearchState, config: RunnableConfig) -> dict:
    """Execute the research plan by searching sources for each section."""
    try:
        mission_id = state["mission_id"]
        plan = state.get("plan", {})
        sections = plan.get("sections", [])
        depth = state.get("depth", "comprehensive")
        num_results = DEPTH_SEARCH_RESULTS.get(depth, 10)

        await _update_mission(mission_id, status="researching", progress=15)

        all_notes = []
        all_log_entries = []
        total_sections = len(sections)

        for i, section in enumerate(sections):
            title = section.get("title", f"Section {i + 1}")
            description = section.get("description", "")
            strategy = section.get("research_strategy", "search_sources")

            section_progress = 15 + int((i / max(total_sections, 1)) * 45)
            await _update_mission(mission_id, progress=section_progress)

            if strategy == "synthesize":
                all_log_entries.append(
                    {
                        "phase": "research",
                        "agent": "researcher",
                        "message": f"Skipping '{title}' (synthesize strategy, handled in writing)",
                    }
                )
                continue

            # Build search queries from section title and description
            search_query = f"{title} {description}"

            try:
                results = await vector_search(search_query, num_results, True, True)
            except Exception as search_err:
                logger.warning(
                    f"Vector search failed for section '{title}': {search_err}"
                )
                results = []

            if not results:
                all_log_entries.append(
                    {
                        "phase": "research",
                        "agent": "researcher",
                        "message": f"No sources found for section '{title}'",
                    }
                )
                all_notes.append(
                    {
                        "section": title,
                        "findings": "No relevant sources found for this section.",
                        "sources": [],
                    }
                )
                continue

            # Build context from search results
            source_texts = []
            source_ids = []
            for r in results:
                record_id = r.get("id", "unknown")
                content = r.get("content", r.get("full_text", r.get("text", "")))
                score = r.get("score", 0)
                if content:
                    source_texts.append(
                        f"[Source: {record_id}, relevance: {score:.2f}]\n{content[:3000]}"
                    )
                    source_ids.append(str(record_id))

            if not source_texts:
                all_notes.append(
                    {
                        "section": title,
                        "findings": "Sources were found but contained no extractable text.",
                        "sources": [],
                    }
                )
                continue

            combined_sources = "\n\n---\n\n".join(source_texts)

            analysis_prompt = f"""You are a research analyst. Analyze the following source content in the context of the research section described below.

Section: {title}
Section Goal: {description}

Extract the key findings relevant to this section. Be specific and cite which source each finding comes from. Organize your findings as a coherent set of research notes.

Source Content:
{combined_sources}

Provide your analysis as a clear, structured set of findings. Focus on facts, data, and insights relevant to the section goal."""

            model = await provision_langchain_model(
                analysis_prompt,
                config.get("configurable", {}).get("model_id")
                or state.get("model_override"),
                "chat",
                max_tokens=3000,
            )

            messages = [
                SystemMessage(content=analysis_prompt),
                HumanMessage(
                    content="Analyze the sources and extract key findings for this research section."
                ),
            ]

            ai_message = await model.ainvoke(messages)
            findings = extract_text_content(ai_message.content)
            findings = clean_thinking_content(findings)

            all_notes.append(
                {
                    "section": title,
                    "findings": findings,
                    "sources": source_ids,
                }
            )

            # Persist note to mission
            mission = await ResearchMission.get(mission_id)
            if mission:
                await mission.add_note(
                    phase="research",
                    content=findings,
                    source_type=strategy,
                    metadata={"section": title, "source_ids": source_ids},
                )

            all_log_entries.append(
                {
                    "phase": "research",
                    "agent": "researcher",
                    "message": f"Researched '{title}': {len(results)} sources found, notes extracted",
                }
            )

        await _update_mission(mission_id, status="researching", progress=60)

        logger.info(
            f"Research completed for mission {mission_id}: "
            f"{len(all_notes)} section notes collected"
        )

        return {
            "notes": all_notes,
            "status": "researching",
            "progress": 60,
            "execution_log": all_log_entries,
        }

    except OpenNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        await _update_mission(
            state["mission_id"],
            status="failed",
            error_message=str(user_message),
        )
        raise error_class(user_message) from e


async def reflection_node(state: ResearchState, config: RunnableConfig) -> dict:
    """Analyze research quality and identify gaps."""
    try:
        mission_id = state["mission_id"]
        plan = state.get("plan", {})
        notes = state.get("notes", [])

        await _update_mission(mission_id, status="reflecting", progress=65)

        # Build a summary of what was researched
        plan_summary = json.dumps(plan, indent=2, default=str)
        notes_summary = "\n\n".join(
            f"### {n.get('section', 'Unknown')}\n{n.get('findings', 'No findings')}"
            for n in notes
        )

        reflection_prompt = f"""You are a research quality analyst. Review the research notes collected so far against the original research plan and assess the quality and completeness of the research.

Research Plan:
{plan_summary}

Research Notes:
{notes_summary}

Analyze the research and provide your assessment as JSON in this exact format:
{{
  "overall_quality": "strong|adequate|weak",
  "coverage_score": 0.0 to 1.0,
  "key_findings": ["Finding 1", "Finding 2"],
  "gaps": ["Gap 1", "Gap 2"],
  "contradictions": ["Contradiction 1"],
  "strengths": ["Strength 1"],
  "suggestions": ["Suggestion for the writing phase"]
}}

Output ONLY valid JSON."""

        model = await provision_langchain_model(
            reflection_prompt,
            config.get("configurable", {}).get("model_id")
            or state.get("model_override"),
            "chat",
            max_tokens=2000,
        )

        messages = [
            SystemMessage(content=reflection_prompt),
            HumanMessage(
                content="Assess the research quality and identify gaps or contradictions."
            ),
        ]

        ai_message = await model.ainvoke(messages)
        content = extract_text_content(ai_message.content)
        cleaned = clean_thinking_content(content)

        # Parse JSON from response
        json_str = cleaned.strip()
        if json_str.startswith("```"):
            json_str = json_str.split("\n", 1)[1] if "\n" in json_str else json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            elif "```" in json_str:
                json_str = json_str[: json_str.rfind("```")]
            json_str = json_str.strip()

        try:
            reflection_data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(
                f"Could not parse reflection JSON for mission {mission_id}, "
                "using raw text"
            )
            reflection_data = {
                "overall_quality": "adequate",
                "coverage_score": 0.5,
                "key_findings": [],
                "gaps": [],
                "contradictions": [],
                "strengths": [],
                "suggestions": [cleaned],
            }

        reflections = [reflection_data]

        # Persist reflection as a research note
        mission = await ResearchMission.get(mission_id)
        if mission:
            await mission.add_note(
                phase="reflection",
                content=json.dumps(reflection_data, indent=2, default=str),
                source_type="reflection",
                metadata={
                    "quality": reflection_data.get("overall_quality", "unknown"),
                    "coverage": reflection_data.get("coverage_score", 0),
                },
            )

        await _update_mission(mission_id, status="reflecting", progress=75)
        await _log_to_mission(
            mission_id,
            "reflection",
            "reviewer",
            f"Research quality: {reflection_data.get('overall_quality', 'unknown')}, "
            f"coverage: {reflection_data.get('coverage_score', 0)}",
        )

        logger.info(
            f"Reflection completed for mission {mission_id}: "
            f"quality={reflection_data.get('overall_quality')}"
        )

        return {
            "reflections": reflections,
            "status": "reflecting",
            "progress": 75,
            "execution_log": [
                {
                    "phase": "reflection",
                    "agent": "reviewer",
                    "message": f"Quality assessment: {reflection_data.get('overall_quality', 'unknown')}",
                }
            ],
        }

    except OpenNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        await _update_mission(
            state["mission_id"],
            status="failed",
            error_message=str(user_message),
        )
        raise error_class(user_message) from e


async def writing_node(state: ResearchState, config: RunnableConfig) -> dict:
    """Produce the final research report from plan, notes, and reflections."""
    try:
        mission_id = state["mission_id"]
        plan = state.get("plan", {})
        notes = state.get("notes", [])
        reflections = state.get("reflections", [])
        query = state["query"]

        await _update_mission(mission_id, status="writing", progress=80)

        # Build context for the writer
        plan_summary = json.dumps(plan, indent=2, default=str)
        notes_text = "\n\n".join(
            f"### {n.get('section', 'Unknown')}\n{n.get('findings', 'No findings')}"
            for n in notes
        )
        reflection_text = ""
        if reflections:
            r = reflections[0]
            reflection_parts = []
            if r.get("key_findings"):
                reflection_parts.append(
                    "Key findings: " + "; ".join(r["key_findings"])
                )
            if r.get("gaps"):
                reflection_parts.append("Gaps identified: " + "; ".join(r["gaps"]))
            if r.get("suggestions"):
                reflection_parts.append(
                    "Suggestions: " + "; ".join(r["suggestions"])
                )
            reflection_text = "\n".join(reflection_parts)

        writing_prompt = f"""You are an expert research writer. Write a comprehensive, well-structured research report based on the research plan, collected notes, and quality assessment below.

Original Research Query: {query}

Research Plan:
{plan_summary}

Research Notes:
{notes_text}

Quality Assessment:
{reflection_text}

Guidelines:
- Write in clear, professional markdown format
- Follow the structure from the research plan
- Incorporate findings from the research notes
- Address any gaps or suggestions from the quality assessment where possible
- Include references to sources where available (use inline citations like [Source: ID])
- Use headers (##) for major sections
- Be comprehensive but concise - avoid filler content
- End with a brief conclusion or summary section

Write the complete research report now."""

        model = await provision_langchain_model(
            writing_prompt,
            config.get("configurable", {}).get("model_id")
            or state.get("model_override"),
            "chat",
            max_tokens=8192,
        )

        messages = [
            SystemMessage(content=writing_prompt),
            HumanMessage(content="Write the research report."),
        ]

        ai_message = await model.ainvoke(messages)
        report = extract_text_content(ai_message.content)
        report = clean_thinking_content(report)

        await _update_mission(mission_id, status="writing", progress=90)

        # Generate summary
        summary_prompt = """You are a summarization assistant. Write a 2-3 sentence summary of the following research report. Capture the main topic, key findings, and conclusion.

Output ONLY the summary text, nothing else."""

        summary_model = await provision_langchain_model(
            summary_prompt,
            config.get("configurable", {}).get("model_id")
            or state.get("model_override"),
            "chat",
            max_tokens=500,
        )

        summary_messages = [
            SystemMessage(content=summary_prompt),
            HumanMessage(content=report),
        ]

        summary_message = await summary_model.ainvoke(summary_messages)
        summary = extract_text_content(summary_message.content)
        summary = clean_thinking_content(summary)

        # Save final results to mission
        await _update_mission(
            mission_id,
            status="completed",
            progress=100,
            report=report,
            summary=summary,
        )
        await _log_to_mission(
            mission_id,
            "writing",
            "writer",
            f"Report completed ({len(report)} characters)",
        )

        logger.info(f"Research report completed for mission {mission_id}")

        return {
            "report": report,
            "summary": summary,
            "status": "completed",
            "progress": 100,
            "execution_log": [
                {
                    "phase": "writing",
                    "agent": "writer",
                    "message": f"Report completed ({len(report)} characters)",
                }
            ],
        }

    except OpenNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        await _update_mission(
            state["mission_id"],
            status="failed",
            error_message=str(user_message),
        )
        raise error_class(user_message) from e


# Build the graph
workflow = StateGraph(ResearchState)

workflow.add_node("planning", planning_node)
workflow.add_node("research", research_node)
workflow.add_node("reflection", reflection_node)
workflow.add_node("writing", writing_node)

workflow.add_edge(START, "planning")
workflow.add_edge("planning", "research")
workflow.add_edge("research", "reflection")
workflow.add_edge("reflection", "writing")
workflow.add_edge("writing", END)

graph = workflow.compile()
