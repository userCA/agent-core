"""End-to-end demo workflow: parallel analyze then summarize."""

meta = {
    "name": "demo-e2e",
    "description": "Analyze items in parallel, then synthesize one summary",
    "phases": ["analyze", "summarize"],
}


async def run(ctx):
    items = list(ctx.args.get("items") or ["alpha", "beta", "gamma"])

    if not ctx.is_phase_done("analyze"):
        await ctx.phase("analyze")
        ctx.log(f"analyzing {len(items)} items")

        async def analyze_one(item, index):
            return await ctx.agent(
                f"Briefly describe item '{item}' in one short sentence.",
                label=f"item-{index}",
            )

        partial = await ctx.pipeline(items, analyze_one)
        ctx.set_phase_output("analyze", partial)
    else:
        partial = ctx.get_phase_output("analyze")

    if not ctx.is_phase_done("summarize"):
        await ctx.phase("summarize")
        summary = await ctx.agent(
            f"Summarize these analyses in one concise sentence:\n{partial}",
            label="summarize",
        )
        ctx.set_phase_output("summarize", summary)
    else:
        summary = ctx.get_phase_output("summarize")

    return {
        "items": items,
        "analyses": partial,
        "summary": summary,
    }
