meta = {
    "name": "adversarial-review",
    "description": "Adversarial author/critic review (args: draft, rubric)",
    "phases": ["verify"],
}


async def run(ctx):
    draft = str(ctx.args.get("draft") or "")
    rubric = str(ctx.args.get("rubric") or "")

    if not ctx.is_phase_done("verify"):
        await ctx.phase("verify")
        result = await adversarial_verify(ctx, draft, rubric)
        ctx.set_phase_output("verify", result)
    else:
        result = ctx.get_phase_output("verify")

    return result
