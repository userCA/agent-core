meta = {
    "name": "sample-bad-import",
    "description": "Workflow with forbidden import",
}

import os


async def run(ctx):
    return os.getcwd()
