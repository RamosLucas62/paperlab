from decimal import Decimal
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # The JevTrader terminal is deliberately pinned to Monad testnet.
    monad_rpc_url: str = "https://rpc.testnet.monad.xyz"
    monad_chain_id: int = 10143
    kuru_ws_url: str = "wss://ws.testnet.kuru.io"
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
    def require_monad_testnet(cls, value: int) -> int:
        if value != 10143:
            raise ValueError("O Terminal JEV está limitado à Monad Testnet (chain ID 10143).")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
