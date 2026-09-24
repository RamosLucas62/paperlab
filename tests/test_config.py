import pytest
from pydantic import ValidationError

from paperlab.config import Settings


def test_terminal_defaults_to_monad_testnet():
    settings = Settings(_env_file=None)
    assert settings.monad_chain_id == 10143
    assert settings.monad_rpc_url == "https://rpc.testnet.monad.xyz"
    assert settings.kuru_ws_url == "wss://ws.testnet.kuru.io"


def test_terminal_rejects_a_non_testnet_chain_id():
    with pytest.raises(ValidationError, match="Monad Testnet"):
        Settings(_env_file=None, monad_chain_id=143)


def test_terminal_rejects_kuru_mainnet_feed():
    with pytest.raises(ValidationError, match="Kuru Testnet"):
        Settings(_env_file=None, kuru_ws_url="wss://ws.kuru.io/")
