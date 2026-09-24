from decimal import Decimal
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


MONAD_NETWORKS = {
    10143: {
        "name": "Monad Testnet",
        "rpc_url": "https://testnet-rpc.monad.xyz",
        "kuru_ws_url": "wss://ws.testnet.kuru.io",
    },
    143: {
        "name": "Monad Mainnet (somente leitura)",
        "rpc_url": "https://rpc.monad.xyz",
        "kuru_ws_url": "wss://ws.kuru.io",
    },
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_mode: str = "demo"
    database_url: str = "sqlite:///./paperlab.db"
    session_secret_key: str = ""
    admin_username: str = ""
    admin_password: str = ""
    cookie_secure: bool = False
    worker_interval_seconds: int = 60
    ai_daily_budget_usd: Decimal = Decimal("2.00")
    ai_call_budget_usd: Decimal = Decimal("0.10")
    max_open_positions: int = 1
    max_order_notional_usd: Decimal = Decimal("100")
    max_daily_orders: int = 6
    max_simulated_drawdown_usd: Decimal = Decimal("500")

    alpaca_data_key_id: str = ""
    alpaca_data_secret_key: str = ""
    alpaca_paper_a_key_id: str = ""
    alpaca_paper_a_secret_key: str = ""
    alpaca_paper_b_key_id: str = ""
    alpaca_paper_b_secret_key: str = ""
    alpaca_paper_c_key_id: str = ""
    alpaca_paper_c_secret_key: str = ""
    openrouter_api_key: str = ""
    openrouter_llm_model: str = ""
    jev_model: str = "typesafe/jev-1.13"
    # Defaults are selected from chain_id. The terminal never signs transactions.
    monad_rpc_url: str = ""
    monad_chain_id: int = 10143
    kuru_ws_url: str = ""
    kuru_market_address: str = ""
    kuru_symbol: str = "MON/USDC"
    terminal_sample_interval_seconds: int = 5
    terminal_jev_interval_seconds: int = 120

    @field_validator("app_mode")
    @classmethod
    def require_safe_application_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "demo":
            raise ValueError("APP_MODE only accepts 'demo'; PAPER is an explicit experiment, and real mode is unsupported.")
        return normalized

    @field_validator("monad_chain_id")
    @classmethod
    def require_supported_monad_network(cls, value: int) -> int:
        if value not in MONAD_NETWORKS:
            raise ValueError("O Terminal JEV só aceita Monad Testnet (10143) ou observação somente leitura na Monad Mainnet (143).")
        return value

    @field_validator("kuru_ws_url")
    @classmethod
    def require_kuru_official_feed(cls, value: str) -> str:
        if not value.strip():
            return ""
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme != "wss"
            or parsed.hostname not in {"ws.testnet.kuru.io", "ws.kuru.io"}
            or parsed.port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("KURU_WS_URL deve usar o feed WSS oficial da Kuru para testnet ou mainnet.")
        return value.strip().rstrip("/")

    @model_validator(mode="after")
    def select_and_validate_market_network(self):
        network = MONAD_NETWORKS[self.monad_chain_id]
        if not self.monad_rpc_url.strip():
            self.monad_rpc_url = network["rpc_url"]
        if not self.kuru_ws_url.strip():
            self.kuru_ws_url = network["kuru_ws_url"]
        expected_host = urlsplit(network["kuru_ws_url"]).hostname
        configured_host = urlsplit(self.kuru_ws_url).hostname
        if configured_host != expected_host:
            raise ValueError(
                f"KURU_WS_URL não corresponde à rede selecionada ({network['name']}; esperado {expected_host})."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
