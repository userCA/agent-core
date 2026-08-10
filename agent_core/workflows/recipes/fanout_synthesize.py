meta = {
    "name": "fanout-synthesize",
    "description": "Map items with sub-agents then synthesize (args: items)",
    "phases": ["fanout", "synthesize"],
}


async def run(ctx):
    items = list(ctx.args.get("items") or [])

    if not ctx.is_phase_done("fanout"):
        await ctx.phase("fanout")

        async def map_item(item, index):
            return await ctx.agent(
                f"Analyze item {index + 1} of {len(items)}:\n{item}",
                profile="worker",
            )

        mapped = await ctx.pipeline(items, map_item)
        ctx.set_phase_output("fanout", mapped)
    else:
        mapped = ctx.get_phase_output("fanout")

    if not ctx.is_phase_done("synthesize"):
        await ctx.phase("synthesize")
        synthesis = await ctx.agent(
            "Synthesize the following analyses into one coherent result:\n"
            + "\n---\n".join(str(row) for row in mapped),
            profile="worker",
        )
        ctx.set_phase_output("synthesize", synthesis)
    else:
        synthesis = ctx.get_phase_output("synthesize")

    return synthesis
