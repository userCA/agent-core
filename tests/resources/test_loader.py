import tempfile
import os

from agent_core.resources.loader import ResourceLoader


def test_resource_loader_search_paths():
    with tempfile.TemporaryDirectory() as d:
        loader = ResourceLoader(cwd=d)
        # No paths exist yet
        assert loader.skill_search_paths == []


def test_resource_loader_load_skills():
    with tempfile.TemporaryDirectory() as d:
        skills_dir = os.path.join(d, ".pi", "skills", "my-skill")
        os.makedirs(skills_dir)
        with open(os.path.join(skills_dir, "SKILL.md"), "w") as f:
            f.write("---\nname: my-skill\ndescription: A skill\n---\n")
        loader = ResourceLoader(cwd=d)
        skills, diagnostics = loader.load_skills()
        assert len(skills) == 1
        assert skills[0].name == "my-skill"
