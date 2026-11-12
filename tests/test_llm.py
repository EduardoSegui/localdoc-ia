from types import SimpleNamespace

import pytest

from localdoc_ia.agent.llm import _response_content_or_raise


def test_empty_response_at_length_explains_how_to_fix_it():
    response = SimpleNamespace(
        message=SimpleNamespace(content=""),
        done_reason="length",
    )

    with pytest.raises(RuntimeError, match="agotó el límite de salida"):
        _response_content_or_raise(
            response,
            "gpt-oss:20b",
            "los datos de la factura",
        )


def test_empty_response_without_length_has_clear_diagnostic():
    response = SimpleNamespace(
        message=SimpleNamespace(content="  "),
        done_reason="stop",
    )

    with pytest.raises(RuntimeError, match="respuesta vacía"):
        _response_content_or_raise(
            response,
            "qwen2.5:7b",
            "los datos de la factura",
        )


def test_response_with_content_is_returned():
    response = SimpleNamespace(
        message=SimpleNamespace(content='{"total": 123}'),
        done_reason="stop",
    )

    assert _response_content_or_raise(
        response,
        "qwen2.5:7b",
        "los datos de la factura",
    ) == '{"total": 123}'
