from agent.prompts.sql_generator import SQL_GENERATOR_SYSTEM


def test_sql_generator_prompt_formats_correctly():
    """Verify SQL_GENERATOR_SYSTEM accepts all expected format placeholders."""
    prompt = SQL_GENERATOR_SYSTEM.format(
        schema_context="schema",
        domain_rules="rules",
        detected_entities="entities",
        user_role="kaprodi",
        few_shot_examples="examples",
    )

    assert "SELECT" in prompt or "schema" in prompt
    assert "{SCOPE_FILTER}" not in prompt
