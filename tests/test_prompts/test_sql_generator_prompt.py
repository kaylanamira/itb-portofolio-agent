from agent.prompts.sql_generator import SQL_GENERATOR_SYSTEM


def test_sql_generator_prompt_formats_with_scope_filter_literal():
    prompt = SQL_GENERATOR_SYSTEM.format(
        schema_context="schema",
        domain_rules="rules",
        detected_entities="entities",
        scope_description="scope",
        scope_hint="hint",
        few_shot_examples="examples",
    )

    assert "{SCOPE_FILTER}" in prompt
