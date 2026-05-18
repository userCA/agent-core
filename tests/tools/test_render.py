from agent_core.tools.render import RenderedOutput


def test_rendered_output_defaults():
    ro = RenderedOutput(text="hello")
    assert ro.text == "hello"
    assert ro.display is None
    assert ro.mime_type == "text/plain"


def test_rendered_output_with_display():
    ro = RenderedOutput(text="hello", display={"code": "python"}, mime_type="text/x-python")
    assert ro.display == {"code": "python"}
    assert ro.mime_type == "text/x-python"
