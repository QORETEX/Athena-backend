"""Tests for skill availability filtering, registration, summaries, and API parity."""
import pytest
from app.skills.base import Skill, SkillInfo, _registry, get_ollama_tools, skills_for


# ── Skill.is_available ────────────────────────────────────────────────────────


def test_is_available_no_check():
    """Skill with no enabled_check is always available."""
    skill = Skill(
        name="_test_no_check",
        description="test",
        parameters={"type": "object", "properties": {}},
    )
    assert skill.is_available() is True


def test_is_available_true_check():
    """Skill with enabled_check returning True is available."""
    skill = Skill(
        name="_test_true",
        description="test",
        parameters={"type": "object", "properties": {}},
        enabled_check=lambda: True,
    )
    assert skill.is_available() is True


def test_is_available_false_check():
    """Skill with enabled_check returning False is unavailable."""
    skill = Skill(
        name="_test_false",
        description="test",
        parameters={"type": "object", "properties": {}},
        enabled_check=lambda: False,
    )
    assert skill.is_available() is False


def test_unavailable_skill_excluded_from_tool_list():
    """A skill with enabled_check=False must not appear in the LLM tool list."""
    test_skill = Skill(
        name="_test_unavailable",
        description="never offered",
        parameters={"type": "object", "properties": {}},
        enabled_check=lambda: False,
        unavailable_reason="test only",
    )

    _registry["_test_unavailable"] = test_skill
    try:
        tool_names = {t["function"]["name"] for t in get_ollama_tools()}
        assert "_test_unavailable" not in tool_names
    finally:
        _registry.pop("_test_unavailable", None)


def test_available_skill_included_in_tool_list():
    """A skill with no enabled_check must appear in the LLM tool list."""
    test_skill = Skill(
        name="_test_available",
        summary="Test skill",
        description="always offered",
        parameters={"type": "object", "properties": {}},
    )

    _registry["_test_available"] = test_skill
    try:
        tool_names = {t["function"]["name"] for t in get_ollama_tools()}
        assert "_test_available" in tool_names
    finally:
        _registry.pop("_test_available", None)


def test_get_unavailable_reason_static():
    """get_unavailable_reason returns the static string."""
    skill = Skill(
        name="_test",
        description="test",
        parameters={"type": "object", "properties": {}},
        enabled_check=lambda: False,
        unavailable_reason="SEARXNG_URL not set",
    )
    assert skill.get_unavailable_reason() == "SEARXNG_URL not set"


def test_get_unavailable_reason_callable():
    """get_unavailable_reason calls a callable reason."""
    skill = Skill(
        name="_test",
        description="test",
        parameters={"type": "object", "properties": {}},
        enabled_check=lambda: False,
        unavailable_reason=lambda: "dynamic reason",
    )
    assert skill.get_unavailable_reason() == "dynamic reason"


# ── register_skill summary validation ────────────────────────────────────────


def test_register_skill_without_summary_raises():
    """register_skill must raise ValueError when summary is empty."""
    from app.skills.base import register_skill

    no_summary = Skill(
        name="_test_no_summary",
        description="test",
        parameters={"type": "object", "properties": {}},
    )
    with pytest.raises(ValueError, match="summary"):
        register_skill(no_summary)

    # Ensure it was not added to the registry
    assert "_test_no_summary" not in _registry


# ── Registration parity ───────────────────────────────────────────────────────


def test_register_all_skills_names_match_startup():
    """Skill names in the registry after startup must equal the pinned expected set.

    The registry is populated by two routes:
    1. register_all_skills() — called by the app lifespan and the conftest fixture.
    2. app/routes/briefing.py — registers daily_briefing as a module-level side
       effect when main.py imports it at startup.

    Pinning the full set here ensures any accidental addition or removal is caught.
    """
    from app.skills.registry import register_all_skills
    from app.skills.base import get_all_skills

    register_all_skills()  # idempotent — already called by the conftest fixture
    names = frozenset(get_all_skills().keys())

    expected = frozenset({
        # Skills registered by register_all_skills() via app/skills/*.py
        "background_research",
        "create_calendar_event",
        "list_calendar_events",
        "device_control",
        "get_device_context",
        "generate_image",
        "search_knowledge",
        "list_skills",
        "remember_fact",
        "forget_fact",
        "forget_all_facts",
        "list_facts",
        "save_note",
        "search_notes",
        "delete_note",
        "set_reminder",
        "list_reminders",
        "control_smart_device",
        "vision",
        "register_face",
        "get_weather",
        "web_search",
        # daily_briefing is registered in app/routes/briefing.py which is
        # imported at module level in main.py → present in the registry
        # by the time any test runs.
        "daily_briefing",
    })

    # Filter out any test-internal sentinel skills injected by other tests
    # (they use names prefixed with "_test_").
    non_test_names = frozenset(n for n in names if not n.startswith("_test_"))

    assert non_test_names == expected, (
        f"Registered skill names do not match startup set.\n"
        f"Extra (in registry but not in expected): {sorted(non_test_names - expected)}\n"
        f"Missing (expected but not in registry): {sorted(expected - non_test_names)}"
    )


# ── Every skill has a non-empty summary ───────────────────────────────────────


def test_all_skills_have_summary():
    """Every registered skill must have a non-empty summary."""
    from app.skills.registry import register_all_skills
    from app.skills.base import get_all_skills

    register_all_skills()
    skills = get_all_skills()
    missing = [
        name for name, s in skills.items()
        if not name.startswith("_test_") and not s.summary
    ]
    assert not missing, f"Skills missing summary: {missing}"


# ── skills_for parity ─────────────────────────────────────────────────────────


def test_skills_for_available_matches_server_tools():
    """skills_for(client_capabilities=False) available names must equal get_server_tools() names."""
    from app.skills.base import get_server_tools
    from app.skills.registry import register_all_skills

    register_all_skills()
    all_infos = skills_for(client_capabilities=False)
    available_names = {s.name for s in all_infos if s.available}

    server_tool_names = {t["function"]["name"] for t in get_server_tools()}

    assert available_names == server_tool_names, (
        f"skills_for available and get_server_tools disagree.\n"
        f"In skills_for but not server_tools: {sorted(available_names - server_tool_names)}\n"
        f"In server_tools but not skills_for: {sorted(server_tool_names - available_names)}"
    )


def test_skills_for_client_capabilities_includes_client_executed():
    """With client_capabilities=True, client_executed skills must be available."""
    from app.skills.registry import register_all_skills

    register_all_skills()
    all_infos = skills_for(client_capabilities=True)
    available_names = {s.name for s in all_infos if s.available}

    assert "device_control" in available_names, "device_control missing from WS tool list"
    assert "create_calendar_event" in available_names, "create_calendar_event missing from WS tool list"


def test_skills_for_http_excludes_client_executed():
    """With client_capabilities=False, client_executed skills must be unavailable."""
    from app.skills.registry import register_all_skills

    register_all_skills()
    all_infos = skills_for(client_capabilities=False)

    for info in all_infos:
        if info.client_executed:
            assert not info.available, (
                f"client_executed skill '{info.name}' must not be available on HTTP path"
            )
            assert info.unavailable_reason is not None


def test_disabled_skills_have_unavailable_reason():
    """Every unavailable skill must include a non-empty unavailable_reason."""
    from app.skills.registry import register_all_skills

    register_all_skills()
    all_infos = skills_for(client_capabilities=False)

    for info in all_infos:
        if not info.available:
            assert info.unavailable_reason, (
                f"Unavailable skill '{info.name}' has no unavailable_reason"
            )


def test_system_prompt_uses_summaries():
    """build_system_prompt with available_skills must use summaries, not descriptions."""
    from app.llm import build_system_prompt

    fake_skills = [
        SkillInfo(
            name="set_reminder",
            summary="Set reminders",
            description="A long description that should not appear.",
            parameters={},
            client_executed=False,
            available=True,
            unavailable_reason=None,
        ),
        SkillInfo(
            name="get_weather",
            summary="Get weather forecast",
            description="Another long description to ignore.",
            parameters={},
            client_executed=False,
            available=True,
            unavailable_reason=None,
        ),
    ]

    prompt = build_system_prompt(available_skills=fake_skills)

    assert "Set reminders" in prompt, "summary 'Set reminders' not in system prompt"
    assert "Get weather forecast" in prompt, "summary 'Get weather forecast' not in system prompt"
    # Descriptions must NOT appear when summaries are provided
    assert "A long description that should not appear." not in prompt
    assert "Another long description to ignore." not in prompt


def test_system_prompt_no_unavailable_skill_summaries():
    """Unavailable skills must not appear in the system prompt capabilities."""
    from app.llm import build_system_prompt

    available = SkillInfo(
        name="set_reminder",
        summary="Set reminders",
        description="...",
        parameters={},
        client_executed=False,
        available=True,
        unavailable_reason=None,
    )
    unavailable = SkillInfo(
        name="web_search",
        summary="Search the web",
        description="...",
        parameters={},
        client_executed=False,
        available=False,
        unavailable_reason="not configured",
    )

    # Only pass the available skill
    prompt = build_system_prompt(available_skills=[available])
    assert "Set reminders" in prompt
    assert "Search the web" not in prompt


# ── GET /api/skills parity with tool list ────────────────────────────────────


def test_api_skills_available_matches_server_tools(authenticated_client):
    """GET /api/skills?available=true must return the same skill names as get_server_tools()."""
    from app.skills.base import get_server_tools

    resp = authenticated_client.get("/api/skills/?available=true")
    assert resp.status_code == 200
    api_names = {s["name"] for s in resp.json()}

    server_tool_names = {t["function"]["name"] for t in get_server_tools()}

    assert api_names == server_tool_names, (
        f"GET /api/skills?available=true and get_server_tools() disagree.\n"
        f"API only: {sorted(api_names - server_tool_names)}\n"
        f"Tools only: {sorted(server_tool_names - api_names)}"
    )


def test_api_skills_all_have_summary_field(authenticated_client):
    """Every skill in GET /api/skills must have a non-empty summary field."""
    resp = authenticated_client.get("/api/skills/")
    assert resp.status_code == 200
    missing = [s["name"] for s in resp.json() if not s.get("summary")]
    assert not missing, f"Skills missing summary in API response: {missing}"


def test_api_skills_unavailable_have_reason(authenticated_client):
    """Unavailable skills in GET /api/skills must carry a non-empty unavailable_reason."""
    resp = authenticated_client.get("/api/skills/")
    assert resp.status_code == 200
    skills = resp.json()
    bad = [
        s["name"] for s in skills
        if not s["available"] and not s.get("unavailable_reason")
    ]
    assert not bad, f"Unavailable skills with no reason: {bad}"


def test_api_skills_filter_available(authenticated_client):
    """GET /api/skills?available=true must only return skills where available=true."""
    resp = authenticated_client.get("/api/skills/?available=true")
    assert resp.status_code == 200
    for skill in resp.json():
        assert skill["available"] is True, (
            f"Skill '{skill['name']}' has available=false but was returned by ?available=true"
        )


def test_api_skills_available_param_false_includes_all(authenticated_client):
    """Without ?available=true the API returns both available and unavailable skills."""
    resp_all = authenticated_client.get("/api/skills/")
    resp_avail = authenticated_client.get("/api/skills/?available=true")
    assert resp_all.status_code == 200
    assert resp_avail.status_code == 200
    assert len(resp_all.json()) >= len(resp_avail.json())


# ── list_skills: client_capabilities context ─────────────────────────────────


@pytest.mark.asyncio
async def test_list_skills_http_excludes_client_executed():
    """list_skills called in HTTP context must not include client-executed skills."""
    from app.chat.pipeline import _client_capabilities
    from app.skills.list_skills import handle_list_skills
    from app.skills.registry import register_all_skills

    register_all_skills()
    token = _client_capabilities.set(False)
    try:
        result = await handle_list_skills()
    finally:
        _client_capabilities.reset(token)

    names = {s["name"] for s in result["skills"]}
    assert "device_control" not in names, "device_control must be absent on HTTP path"
    assert "create_calendar_event" not in names
    assert "list_calendar_events" not in names
    # The skill must not list itself
    assert "list_skills" not in names


@pytest.mark.asyncio
async def test_list_skills_ws_includes_client_executed():
    """list_skills called in WS context must include client-executed skills."""
    from app.chat.pipeline import _client_capabilities
    from app.skills.list_skills import handle_list_skills
    from app.skills.registry import register_all_skills

    register_all_skills()
    token = _client_capabilities.set(True)
    try:
        result = await handle_list_skills()
    finally:
        _client_capabilities.reset(token)

    names = {s["name"] for s in result["skills"]}
    assert "device_control" in names, "device_control must be present on WS path"
    assert "create_calendar_event" in names
    # Still must not list itself
    assert "list_skills" not in names


@pytest.mark.asyncio
async def test_list_skills_matches_api_skills_http(authenticated_client):
    """list_skills result (HTTP context) must equal GET /api/skills?available=true names minus list_skills."""
    from app.chat.pipeline import _client_capabilities
    from app.skills.list_skills import handle_list_skills
    from app.skills.registry import register_all_skills

    register_all_skills()

    api_resp = authenticated_client.get("/api/skills/?available=true&client_capabilities=false")
    assert api_resp.status_code == 200
    # API includes list_skills itself; handler filters it out, so exclude it for comparison.
    api_names = {s["name"] for s in api_resp.json()} - {"list_skills"}

    token = _client_capabilities.set(False)
    try:
        result = await handle_list_skills()
    finally:
        _client_capabilities.reset(token)
    handler_names = {s["name"] for s in result["skills"]}

    assert handler_names == api_names, (
        f"list_skills handler and GET /api/skills disagree (HTTP context).\n"
        f"Handler only: {sorted(handler_names - api_names)}\n"
        f"API only: {sorted(api_names - handler_names)}"
    )


@pytest.mark.asyncio
async def test_list_skills_ws_matches_api_skills_client_caps(authenticated_client):
    """list_skills result (WS context) must equal GET /api/skills?available=true&client_capabilities=true names minus list_skills."""
    from app.chat.pipeline import _client_capabilities
    from app.skills.list_skills import handle_list_skills
    from app.skills.registry import register_all_skills

    register_all_skills()

    api_resp = authenticated_client.get("/api/skills/?available=true&client_capabilities=true")
    assert api_resp.status_code == 200
    api_names = {s["name"] for s in api_resp.json()} - {"list_skills"}

    token = _client_capabilities.set(True)
    try:
        result = await handle_list_skills()
    finally:
        _client_capabilities.reset(token)
    handler_names = {s["name"] for s in result["skills"]}

    assert handler_names == api_names, (
        f"list_skills handler and GET /api/skills disagree (WS/client_capabilities context).\n"
        f"Handler only: {sorted(handler_names - api_names)}\n"
        f"API only: {sorted(api_names - handler_names)}"
    )
