import agent_core.prompts as prompts


def test_prompts_exports():
    assert hasattr(prompts, "SystemPrompt")
    assert hasattr(prompts, "SystemPromptBuilder")
    assert hasattr(prompts, "SystemPromptSection")
    assert hasattr(prompts, "extract_snippet")
    assert hasattr(prompts, "generate_guidelines")


def test_prompts_all():
    assert set(prompts.__all__) == {
        "SystemPrompt",
        "SystemPromptBuilder",
        "SystemPromptSection",
        "extract_snippet",
        "generate_guidelines",
    }
