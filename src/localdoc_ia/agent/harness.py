
import json
import logging
from dataclasses import dataclass
from typing import Any

from mcp import Client
from mcp.server import MCPServer
from mcp.types import TextContent
from ollama import AsyncClient

from localdoc_ia.agent.context import AgentContext
from localdoc_ia.agent.prompts import build_agent_system_prompt
from localdoc_ia.config import settings
from localdoc_ia.mcp.server import mcp as localdoc_mcp_server


logger = logging.getLogger(__name__)

MAX_TOOL_CALLS_PER_ROUND = 5


@dataclass
class AgentResponse:
    """Resultado final de una ejecución del agente."""

    answer: str
    tools_used: list[str]
    model_calls: int
    tool_rounds: int


def convert_mcp_tools_to_ollama(
    mcp_tools: list[Any],
) -> list[dict[str, Any]]:
    """
    Convierte las definiciones de herramientas MCP
    al formato de herramientas de Ollama.
    """

    ollama_tools = []

    for tool in mcp_tools:
        parameters = tool.input_schema or {
            "type": "object",
            "properties": {},
        }

        ollama_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": (
                        tool.description
                        or getattr(tool, "title", None)
                        or tool.name
                    ),
                    "parameters": parameters,
                },
            }
        )

    return ollama_tools


def serialize_tool_result(result: Any) -> str:
    """
    Convierte la respuesta MCP en texto JSON
    para incorporarla al historial de Ollama.
    """

    if result.is_error:
        error_messages = []

        for block in result.content:
            if isinstance(block, TextContent):
                error_messages.append(block.text)

        payload = {
            "error": True,
            "messages": error_messages or [
                "La herramienta MCP devolvió un error."
            ],
        }

    elif result.structured_content is not None:
        payload = result.structured_content

    else:
        content_items = []

        for block in result.content:
            if isinstance(block, TextContent):
                content_items.append(block.text)
            elif hasattr(block, "model_dump"):
                content_items.append(
                    block.model_dump(mode="json")
                )
            else:
                content_items.append(str(block))

        payload = {
            "content": content_items,
        }

    return json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
    )


async def list_all_mcp_tools(
    client: Client,
) -> list[Any]:
    """
    Obtiene todas las herramientas MCP.

    Soporta paginación mediante next_cursor.
    """

    tools = []
    cursor = None

    while True:
        page = await client.list_tools(cursor=cursor)

        tools.extend(page.tools)

        if page.next_cursor is None:
            break

        cursor = page.next_cursor

    return tools


class AgentHarness:
    """
    Orquestador principal del agente.

    Conecta Ollama con un servidor MCP y administra
    el ciclo de razonamiento y ejecución de herramientas.
    """

    def __init__(
        self,
        ollama_client: Any | None = None,
        mcp_server: MCPServer | None = None,
        context: AgentContext | None = None,
        max_tool_rounds: int | None = None,
    ) -> None:

        self._owns_ollama_client = ollama_client is None

        self.ollama_client = (
            ollama_client
            if ollama_client is not None
            else AsyncClient(host=settings.ollama_host)
        )

        self.mcp_server = (
            mcp_server
            if mcp_server is not None
            else localdoc_mcp_server
        )

        self.context = (
            context
            if context is not None
            else AgentContext(
                max_turns=settings.max_conversation_turns
            )
        )

        self.max_tool_rounds = (
            max_tool_rounds
            if max_tool_rounds is not None
            else settings.max_agent_steps
        )

        if self.max_tool_rounds < 1:
            raise ValueError(
                "max_tool_rounds debe ser al menos 1."
            )

    async def ask(self, user_message: str) -> AgentResponse:
        """
        Ejecuta una consulta del usuario mediante el Agent Loop.

        El agente puede ejecutar herramientas MCP y volver
        a consultar Ollama hasta producir una respuesta final.
        """

        system_prompt = build_agent_system_prompt()

        messages = self.context.build_messages(
            system_prompt=system_prompt,
            user_message=user_message,
        )

        tools_used: list[str] = []
        model_calls = 0
        tool_rounds = 0

        # Conectar con el servidor MCP.
        # La conexión en memoria utiliza el protocolo MCP real.
        async with Client(self.mcp_server) as mcp_client:

            # 1. Descubrir herramientas disponibles
            mcp_tools = await list_all_mcp_tools(mcp_client)

            if not mcp_tools:
                raise RuntimeError(
                    "El servidor MCP no publicó ninguna herramienta."
                )

            # 2. Convertir herramientas a formato Ollama
            ollama_tools = convert_mcp_tools_to_ollama(mcp_tools)

            available_tool_names = {
                tool.name for tool in mcp_tools
            }

            logger.info(
                "Herramientas MCP disponibles: %s",
                sorted(available_tool_names),
            )

            # 3. Agent Loop
            # Hay una llamada final adicional para que el modelo
            # responda después de ejecutar hasta N rondas.
            for round_index in range(self.max_tool_rounds + 1):

                try:
                    response = await self.ollama_client.chat(
                        model=settings.ollama_model,
                        messages=messages,
                        tools=ollama_tools,
                        options={
                            "temperature": settings.ollama_temperature,
                        },
                        stream=False,
                    )

                except Exception as error:
                    logger.exception("Error consultando Ollama.")

                    raise RuntimeError(
                        "No se pudo obtener una respuesta de Ollama. "
                        "Verificá que el servidor esté activo y "
                        "que el modelo esté instalado."
                    ) from error

                model_calls += 1

                assistant_message = response.message
                tool_calls = assistant_message.tool_calls or []

                # Incorporar el mensaje completo del asistente.
                # Es importante conservar tool_calls para que
                # Ollama entienda qué herramientas solicitó.
                messages.append(assistant_message)

                # 4. Si no hay llamadas a herramientas,
                # el modelo terminó de responder.
                if not tool_calls:

                    answer = (
                        assistant_message.content or ""
                    ).strip()

                    if not answer:
                        answer = (
                            "No pude generar una respuesta textual "
                            "para esta consulta."
                        )

                    self.context.remember_exchange(
                        user_message=user_message,
                        assistant_message=answer,
                    )

                    return AgentResponse(
                        answer=answer,
                        tools_used=tools_used,
                        model_calls=model_calls,
                        tool_rounds=tool_rounds,
                    )

                # 5. Comprobar límite de rondas
                if round_index == self.max_tool_rounds:

                    answer = (
                        f"Alcancé el límite de "
                        f"{self.max_tool_rounds} rondas de herramientas. "
                        "La consulta quedó incompleta. "
                        "Podés reformularla para continuar."
                    )

                    self.context.remember_exchange(
                        user_message=user_message,
                        assistant_message=answer,
                    )

                    return AgentResponse(
                        answer=answer,
                        tools_used=tools_used,
                        model_calls=model_calls,
                        tool_rounds=tool_rounds,
                    )

                tool_rounds += 1

                # 6. Ejecutar cada herramienta solicitada
                for index, tool_call in enumerate(tool_calls):

                    tool_name = tool_call.function.name
                    arguments = tool_call.function.arguments or {}

                    logger.info(
                        "Solicitud de herramienta MCP: %s",
                        tool_name,
                    )

                    # Protección ante herramientas desconocidas
                    if tool_name not in available_tool_names:
                        tool_output = json.dumps(
                            {
                                "error": True,
                                "message": (
                                    f"La herramienta '{tool_name}' "
                                    "no está disponible."
                                ),
                            },
                            ensure_ascii=False,
                        )

                    # Limitar llamadas por ronda
                    elif index >= MAX_TOOL_CALLS_PER_ROUND:
                        tool_output = json.dumps(
                            {
                                "error": True,
                                "message": (
                                    "Se alcanzó el máximo de "
                                    "herramientas permitido por ronda."
                                ),
                            },
                            ensure_ascii=False,
                        )

                    elif not isinstance(arguments, dict):
                        tool_output = json.dumps(
                            {
                                "error": True,
                                "message": (
                                    "Los argumentos de la herramienta "
                                    "no tienen un formato válido."
                                ),
                            },
                            ensure_ascii=False,
                        )

                    else:
                        try:
                            # Ejecutar mediante el protocolo MCP
                            result = await mcp_client.call_tool(
                                tool_name,
                                arguments,
                            )

                            tool_output = serialize_tool_result(
                                result
                            )

                            tools_used.append(tool_name)

                        except Exception as error:
                            logger.exception(
                                "Error ejecutando herramienta %s",
                                tool_name,
                            )

                            tool_output = json.dumps(
                                {
                                    "error": True,
                                    "message": (
                                        f"No se pudo ejecutar "
                                        f"{tool_name}: {str(error)}"
                                    ),
                                },
                                ensure_ascii=False,
                            )

                    # 7. Devolver el resultado al modelo.
                    # Este paso es fundamental para completar
                    # el ciclo de razonamiento.
                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": tool_name,
                            "content": tool_output,
                        }
                    )

        # Respaldo defensivo. Normalmente el flujo retorna dentro
        # del bucle o al alcanzar el límite.
        raise RuntimeError(
            "El Agent Loop finalizó sin producir una respuesta."
        )

    async def aclose(self) -> None:
        """Cierra el cliente Ollama si fue creado por este agente."""

        if self._owns_ollama_client:
            await self.ollama_client.close()
