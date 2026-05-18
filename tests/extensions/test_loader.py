from agent_core.extensions.loader import ExtensionLoader


def test_extension_loader_empty_specs():
    loader = ExtensionLoader()
    extensions = loader.load_from_specs([])
    assert extensions == []
