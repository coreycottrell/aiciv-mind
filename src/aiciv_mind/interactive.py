"""Interactive REPL for aiciv-mind primary mind."""
import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiciv_mind.mind import Mind

logger = logging.getLogger(__name__)


class InteractiveREPL:
    """
    Interactive command-line interface for a Mind.
    Reads prompts from stdin, runs Mind.run_task(), prints response.
    """

    COMMANDS = {
        "/quit": "Exit the REPL",
        "/exit": "Exit the REPL",
        "/help": "Show this help",
        "/status": "Show mind status",
        "/clear": "Clear conversation history",
        "/memories [query]": "Search memories",
    }

    def __init__(self, mind: "Mind") -> None:
        self.mind = mind
        self._running = True

    async def run(self) -> None:
        """Main REPL loop."""
        self._print_banner()
        while self._running:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, self._readline
                )
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break

            line = line.strip()
            if not line:
                continue

            if line.startswith("/"):
                handled = await self._handle_command(line)
                if not handled:
                    print("Unknown command. Type /help for available commands.")
                continue

            # Run the task through the mind
            try:
                print()  # blank line before response
                result = await self.mind.run_task(line)
                print(f"\n{result}\n")
            except KeyboardInterrupt:
                print("\n[Interrupted]")
                self.mind.stop()
            except Exception as e:
                print(f"\nERROR: {e}\n")
                logger.exception("Error during task execution")

    def _readline(self) -> str:
        """Blocking readline — runs in executor."""
        try:
            return input(f"\n[{self.mind.manifest.mind_id}] > ")
        except EOFError:
            raise

    def _print_banner(self) -> None:
        m = self.mind.manifest
        print(f"\n{'='*60}")
        print(f"  aiciv-mind v0.1")
        print(f"  Mind:  {m.display_name}")
        print(f"  Model: {m.model.preferred}")
        print(f"  Tools: {', '.join(m.enabled_tool_names())}")
        print(f"{'='*60}")
        print("  Type a prompt to interact. /help for commands.")
        print(f"{'='*60}\n")

    async def _handle_command(self, line: str) -> bool:
        """Handle / commands. Returns True if command was recognized."""
        parts = line.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit"):
            self._running = False
            print("Goodbye.")
            return True

        if cmd == "/help":
            print("\nAvailable commands:")
            for cmd_name, desc in self.COMMANDS.items():
                print(f"  {cmd_name:<25} {desc}")
            print()
            return True

        if cmd == "/status":
            m = self.mind.manifest
            print(f"\nMind: {m.mind_id} ({m.role})")
            print(f"Model: {m.model.preferred}")
            print(f"Tools: {', '.join(m.enabled_tool_names())}")
            print(f"Messages in history: {len(self.mind._messages)}")
            print()
            return True

        if cmd == "/clear":
            # Write handoff memory before clearing so next session knows what was in progress
            try:
                from aiciv_mind.memory import Memory
                last_msgs = self.mind._messages
                last_text = "(empty)"
                for msg in reversed(last_msgs):
                    if msg.get("role") != "assistant":
                        continue
                    content = msg.get("content", "")
                    if isinstance(content, str) and content.strip():
                        last_text = content[:400]
                        break
                    if isinstance(content, list):
                        for block in reversed(content):
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "").strip()
                                if text:
                                    last_text = text[:400]
                                    break
                        if last_text != "(empty)":
                            break
                handoff = Memory(
                    agent_id=self.mind.manifest.mind_id,
                    title="Context cleared — mid-session handoff",
                    content=(
                        f"Conversation cleared mid-session by /clear command.\n"
                        f"Turn count before clear: {len(last_msgs)}\n"
                        f"Last assistant response: {last_text}"
                    ),
                    memory_type="handoff",
                    tags=["handoff", "clear"],
                )
                self.mind.memory.store(handoff)
            except Exception:
                pass  # Never block /clear due to memory errors
            self.mind.clear_history()
            print("Conversation history cleared. Handoff memory written.")
            return True

        if cmd == "/memories":
            query = args or "recent"
            results = self.mind.memory.search(
                query=query,
                agent_id=self.mind.manifest.mind_id,
                limit=5,
            )
            if results:
                print(f"\nMemories matching '{query}':")
                for m in results:
                    print(f"\n  [{m.get('memory_type', '?')}] {m.get('title', '?')}")
                    content = m.get("content", "")
                    if len(content) > 200:
                        content = content[:200] + "..."
                    print(f"  {content}")
                print()
            else:
                print(f"No memories found for '{query}'")
            return True

        return False
