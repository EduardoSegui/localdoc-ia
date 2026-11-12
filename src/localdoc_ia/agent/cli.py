
import asyncio

from localdoc_ia.agent.context import AgentContext
from localdoc_ia.agent.harness import AgentHarness
from localdoc_ia.config import settings


async def main() -> None:
    """Inicia una sesión conversacional con el agente."""

    context = AgentContext(
        max_turns=settings.max_conversation_turns
    )

    agent = AgentHarness(
        context=context,
    )

    print("=" * 60)
    print(settings.app_name.upper())
    print("Asistente inteligente de gestión documental")
    print("=" * 60)

    print("\nModelo:", settings.ollama_model)
    print("Herramientas: MCP")
    print("\nComandos:")
    print("  /salir  - Finalizar conversación")
    print("  /reset  - Borrar el contexto conversacional")

    try:
        while True:
            try:
                user_message = input("\nVos: ").strip()

            except EOFError:
                break

            if not user_message:
                continue

            if user_message.lower() in {"/salir", "/exit", "/quit"}:
                print(f"\n{settings.app_name}: ¡Hasta luego!")
                break

            if user_message.lower() == "/reset":
                context.clear()
                print(f"\n{settings.app_name}: Contexto reiniciado.")
                continue

            try:
                result = await agent.ask(user_message)

                print(f"\n{settings.app_name}: {result.answer}")

                if result.tools_used:
                    print(
                        "\n[Herramientas utilizadas: "
                        + ", ".join(result.tools_used)
                        + "]"
                    )

                print(
                    f"[Llamadas al modelo: {result.model_calls} | "
                    f"Rondas de herramientas: {result.tool_rounds}]"
                )

            except Exception as error:
                print(f"\nError: {error}")

    finally:
        await agent.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nConversación interrumpida.")
