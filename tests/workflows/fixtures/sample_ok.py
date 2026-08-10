meta = {
    "name": "sample-ok",
    "description": "Sample OK workflow",
    "phases": ["p1"],
}


async def run(ctx):
    await ctx.phase("p1")
    ctx.log("hi")
    return {"ok": True}
