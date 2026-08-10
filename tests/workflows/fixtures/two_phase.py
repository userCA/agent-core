meta = {
    "name": "two-phase",
    "description": "Two-phase resume demo",
    "phases": ["A", "B"],
}


async def run(ctx):
    if not ctx.is_phase_done("A"):
        await ctx.phase("A")
        ctx.set_phase_output("A", "doneA")
    if not ctx.is_phase_done("B"):
        await ctx.phase("B")
        await ctx.agent("phase B task", profile="worker")
        ctx.set_phase_output("B", "doneB")
    return {"A": ctx.get_phase_output("A"), "B": ctx.get_phase_output("B")}
