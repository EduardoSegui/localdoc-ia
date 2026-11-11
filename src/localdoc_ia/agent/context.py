
from dataclasses import dataclass, field


@dataclass
class AgentContext:
    """
    Administra la memoria temporal de una conversación.

    Solo conserva mensajes del usuario y respuestas finales
    del asistente. Los mensajes internos de herramientas MCP
    se mantienen dentro de cada ejecución del Agent Loop.
    """

    max_turns: int = 6

    history: list[dict[str, str]] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        if self.max_turns < 1:
            raise ValueError(
                "max_turns debe ser al menos 1."
            )

    def build_messages(
        self,
        system_prompt: str,
        user_message: str,
    ) -> list[dict[str, str]]:
        """
        Construye los mensajes que se envían al modelo.

        Orden:
        1. System prompt.
        2. Historial anterior.
        3. Mensaje actual.
        """

        if not user_message or not user_message.strip():
            raise ValueError(
                "El mensaje del usuario no puede estar vacío."
            )

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

        # Copiamos el historial para no modificarlo
        # durante la ejecución del Agent Loop.
        messages.extend(
            dict(message)
            for message in self.history
        )

        messages.append(
            {
                "role": "user",
                "content": user_message.strip(),
            }
        )

        return messages

    def remember_exchange(
        self,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """
        Guarda el intercambio final de la conversación.

        Mantiene únicamente los últimos max_turns intercambios.
        """

        self.history.extend(
            [
                {
                    "role": "user",
                    "content": user_message.strip(),
                },
                {
                    "role": "assistant",
                    "content": assistant_message.strip(),
                },
            ]
        )

        max_messages = self.max_turns * 2

        self.history = self.history[-max_messages:]

    def clear(self) -> None:
        """Elimina todo el historial de la conversación."""

        self.history.clear()
