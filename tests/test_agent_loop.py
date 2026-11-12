
from types import SimpleNamespace

import pytest

from mcp.server import MCPServer

from localdoc_ia.agent.context import AgentContext
from localdoc_ia.agent.harness import AgentHarness
from localdoc_ia.agent import harness as harness_module
from localdoc_ia.agent.harness import serialize_tool_result


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeOllamaClient:
    """Simula dos respuestas consecutivas de Ollama."""

    def __init__(self):
        self.calls = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)

        if len(self.calls) == 1:
            # Primera respuesta: el modelo solicita una herramienta.
            tool_call = SimpleNamespace(
                function=SimpleNamespace(
                    name="buscar_documentos",
                    arguments={"termino": "Proveedor Demo"},
                )
            )

            message = SimpleNamespace(
                content="",
                tool_calls=[tool_call],
            )

        else:
            # Segunda respuesta: el modelo recibe el resultado
            # de MCP y formula la respuesta final.
            message = SimpleNamespace(
                content="Encontré una factura del Proveedor Demo.",
                tool_calls=[],
            )

        return SimpleNamespace(message=message)


@pytest.mark.anyio
async def test_agent_loop_executes_mcp_tool_and_returns_answer():

    # Crear un servidor MCP aislado para esta prueba.
    test_server = MCPServer("LocalDoc Test")

    @test_server.tool()
    def buscar_documentos(termino: str) -> dict:
        """Busca documentos ficticios para la prueba."""

        return {
            "total_encontrados": 1,
            "documentos": [
                {
                    "proveedor": termino,
                    "total": "100000.00",
                    "moneda": "ARS",
                }
            ],
        }

    fake_ollama = FakeOllamaClient()

    context = AgentContext(max_turns=3)

    agent = AgentHarness(
        ollama_client=fake_ollama,
        mcp_server=test_server,
        context=context,
        max_tool_rounds=2,
    )

    result = await agent.ask(
        "Buscá las facturas del Proveedor Demo."
    )

    # El resultado final debe provenir de la segunda respuesta.
    assert result.answer == (
        "Encontré una factura del Proveedor Demo."
    )

    # Ollama tuvo que ser consultado dos veces.
    assert result.model_calls == 2

    # Se ejecutó una ronda de herramientas.
    assert result.tool_rounds == 1

    # La herramienta MCP fue ejecutada.
    assert "buscar_documentos" in result.tools_used

    # Comprobar que el resultado MCP volvió al modelo.
    second_call_messages = fake_ollama.calls[1]["messages"]

    # El contexto debe configurarse explícitamente para que el prompt,
    # las herramientas y los resultados MCP entren en la ventana del modelo.
    options = fake_ollama.calls[0]["options"]
    assert options["num_ctx"] >= 8192
    assert options["num_predict"] > 0

    tool_messages = [
        message
        for message in second_call_messages
        if isinstance(message, dict)
        and message.get("role") == "tool"
    ]

    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_name"] == "buscar_documentos"
    assert "Proveedor Demo" in tool_messages[0]["content"]

    # Comprobar que el intercambio quedó en memoria.
    assert len(context.history) == 2

    assert context.history[0]["role"] == "user"
    assert context.history[1]["role"] == "assistant"

    await agent.aclose()

def test_context_limits_conversation_history():

    context = AgentContext(max_turns=2)

    context.remember_exchange("Pregunta 1", "Respuesta 1")
    context.remember_exchange("Pregunta 2", "Respuesta 2")
    context.remember_exchange("Pregunta 3", "Respuesta 3")

    assert len(context.history) == 4

    assert context.history[0]["content"] == "Pregunta 2"
    assert context.history[-1]["content"] == "Respuesta 3"


def test_serialize_tool_result_truncates_large_payloads(monkeypatch):
    """Evita enviar resultados MCP que superen la ventana del modelo."""

    monkeypatch.setattr(
        harness_module.settings,
        "max_tool_result_chars",
        100,
    )

    result = SimpleNamespace(
        is_error=False,
        structured_content={"texto": "x" * 500},
        content=[],
    )

    serialized = serialize_tool_result(result)

    assert "resultado truncado por tamaño" in serialized
    assert len(serialized) < 200
