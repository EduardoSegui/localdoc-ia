from pathlib import Path

from localdoc_ia.config import Settings


def test_settings_reads_application_and_path_variables(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("APP_NAME", "Asistente de Prueba")
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("INBOX_DIR", str(tmp_path / "inbox"))
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path / "samples"))
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("OCR_LANG", "eng")
    monkeypatch.setenv("OCR_DPI", "150")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434")

    settings = Settings(_env_file=None)

    assert settings.app_name == "Asistente de Prueba"
    assert settings.app_env == "testing"
    assert settings.log_level == "DEBUG"
    assert settings.inbox_path == tmp_path / "inbox"
    assert settings.samples_path == tmp_path / "samples"
    assert settings.reports_path == tmp_path / "reports"
    assert settings.ocr_lang == "eng"
    assert settings.ocr_dpi == 150
    assert settings.ollama_host == "http://ollama.test:11434"


def test_document_subdirectories_default_to_documents_dir(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path / "documentos"))
    monkeypatch.delenv("INBOX_DIR", raising=False)
    monkeypatch.delenv("SAMPLES_DIR", raising=False)

    settings = Settings(_env_file=None)

    assert settings.inbox_path == tmp_path / "documentos" / "inbox"
    assert settings.samples_path == tmp_path / "documentos" / "samples"


def test_relative_paths_resolve_from_project_root(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("INBOX_DIR", "./data/inbox")
    monkeypatch.setenv("REPORTS_DIR", "./reports")

    settings = Settings(_env_file=None)

    assert settings.inbox_path.is_absolute()
    assert settings.reports_path.is_absolute()
    assert settings.inbox_path.name == "inbox"
    assert settings.reports_path.name == "reports"
    assert Path(settings.inbox_path).is_absolute()
