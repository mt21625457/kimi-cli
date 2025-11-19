from __future__ import annotations

from pathlib import Path

from kimi_http.models import RunRequest


def test_run_request_normalizes_paths_and_env(tmp_path):
    agent_file = tmp_path / "agent.yaml"
    agent_file.write_text("name: test")

    payload = {
        "command": " list files ",
        "work_dir": str(tmp_path),
        "agent_file": str(agent_file),
        "env": {
            "kimi_base_url": "https://api.example.com",
            "KIMI_API_KEY": "sk-123",
            "": "ignored",
        },
    }

    request = RunRequest.model_validate(payload)

    assert request.work_dir == tmp_path.resolve()
    assert request.agent_file == agent_file.resolve()
    assert request.env == {
        "KIMI_BASE_URL": "https://api.example.com",
        "KIMI_API_KEY": "sk-123",
    }
    assert request.command.strip() == "list files"
