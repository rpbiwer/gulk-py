import asyncio

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query


async def main():
    # Agentic loop: streams messages as Claude works
    async for message in query(
        prompt="Can you create a plan for implementing step 1 of @docs/plans/playable-ui.md ?",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Edit", "Bash"],
            permission_mode="plan",
            model="claude-sonnet-5",
            max_budget_usd=2,
        ),
    ):
        # Print human-readable output
        print(repr(message))
        # if isinstance(message, AssistantMessage):
        #     for block in message.content:
        #         if hasattr(block, "text"):
        #             print(block.text)  # Claude's reasoning
        #         elif hasattr(block, "name"):
        #             print(f"Tool: {block.name}")  # Tool being called
        # elif isinstance(message, ResultMessage):
        #     print(f"Done: {message.subtype}")  # Final result


asyncio.run(main())
