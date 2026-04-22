from pathlib import Path


def test_start_project_script_exists_and_targets_project_processes():
    script_path = Path("start_project.ps1")

    assert script_path.exists()

    content = script_path.read_text(encoding="utf-8")
    assert ".venv" in content
    assert "api_solver.py" in content
    assert "grok.py" in content
    assert "Start-Process" in content
    assert "param(" in content
    assert "[int]$Thread = 2" in content
    assert "[switch]$NoSolverDebug" in content
    assert "[switch]$OnlySolver" in content
    assert "[switch]$OnlyMain" in content
    assert "--thread $Thread" in content
    assert '--debug"' in content or "--debug'" in content
    assert "if (-not $OnlyMain)" in content
    assert "if (-not $OnlySolver)" in content


def test_batch_launcher_exists_and_invokes_powershell_script():
    launcher_path = Path("start_project.bat")

    assert launcher_path.exists()

    content = launcher_path.read_text(encoding="utf-8")
    assert "start_project.ps1" in content
    assert "Set-ExecutionPolicy -Scope Process Bypass" in content
    assert "%~dp0" in content
