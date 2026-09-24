import pytest
from pydantic import ValidationError

from paperlab.config import Settings


def test_terminal_defaults_to_monad_testnet():
    settings = Settings(_env_file=None)
    assert settings.monad_chain_id == 10143
    assert settings.monad_rpc_url == "https://testnet-rpc.monad.xyz"
    assert settings.kuru_ws_url == "wss://ws.testnet.kuru.io"


def test_terminal_selects_monad_mainnet_read_only_defaults():
    settings = Settings(_env_file=None, monad_chain_id=143)
    assert settings.monad_rpc_url == "https://rpc.monad.xyz"
    assert settings.kuru_ws_url == "wss://ws.kuru.io"


def test_terminal_rejects_an_unsupported_chain_id():
    with pytest.raises(ValidationError, match="só aceita Monad Testnet"):
        Settings(_env_file=None, monad_chain_id=8453)


def test_terminal_rejects_kuru_feed_from_the_other_network():
    with pytest.raises(ValidationError, match="não corresponde à rede selecionada"):
        Settings(_env_file=None, monad_chain_id=10143, kuru_ws_url="wss://ws.kuru.io/")
    with pytest.raises(ValidationError, match="não corresponde à rede selecionada"):
        Settings(_env_file=None, monad_chain_id=143, kuru_ws_url="wss://ws.testnet.kuru.io/")
