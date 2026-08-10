meta = {
    "name": "pipeline-demo",
    "description": "Pipeline with agent calls",
    "phases": ["work"],
}


async def run(ctx):
    await ctx.phase("work")
    n = int(ctx.args.get("n", 0))

    async def fn(i, idx):
        return await ctx.agent(f"task {i}", profile="worker")

    results = await ctx.pipeline(list(range(n)), fn)
    ctx.set_phase_output("work", results)
    return {"count": len(results)}
