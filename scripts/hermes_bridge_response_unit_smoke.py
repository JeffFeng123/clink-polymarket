import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient

from services.hermes_bridge_service.app import app


def _fake_hermes_script(name: str, body: str) -> str:
    path = Path('/tmp') / name
    path.write_text(f'#!/usr/bin/env bash\nprintf %s {body!r}\n')
    path.chmod(0o755)
    return str(path)


def test_placeholder_agent_message_is_not_returned_verbatim() -> None:
    command = _fake_hermes_script(
        'fake_hermes_placeholder.sh',
        'Hermes placeholder output\n{"bridge_mode":"hermes_cli","status":"chat_response","agent_messages":["..."]}',
    )
    os.environ['HERMES_BRIDGE_COMMAND'] = command
    client = TestClient(app)

    response = client.post('/message', json={'message': '你是谁', 'amount_usdc': '1'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['request_id'].startswith('hmsg_')
    assert payload['hermes_received'] is True
    assert payload['agent_messages']
    assert payload['agent_messages'][0] != '...'
    assert 'placeholder' in payload['agent_messages'][0].lower()


def test_real_agent_message_passes_through() -> None:
    command = _fake_hermes_script(
        'fake_hermes_real_message.sh',
        '{"bridge_mode":"hermes_cli","status":"chat_response","agent_messages":["我是 Hermes，已经连到 Clink。"]}',
    )
    os.environ['HERMES_BRIDGE_COMMAND'] = command
    client = TestClient(app)

    response = client.post('/message', json={'message': '你是谁', 'amount_usdc': '1'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'chat_response'
    assert payload['agent_messages'][0] == '我是 Hermes，已经连到 Clink。'


if __name__ == '__main__':
    test_placeholder_agent_message_is_not_returned_verbatim()
    test_real_agent_message_passes_through()
    print('{"status": "ok"}')
