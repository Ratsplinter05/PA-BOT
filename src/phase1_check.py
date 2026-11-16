
from src.config import load_settings
from src.mt5_connection import MT5Connection
from src.market_data import MarketData
from src.data_validation import CandleValidator
from src.logger import get_logger


log = get_logger("PHASE1")

SYMBOL_CANDIDATES = {
    "XAUUSD": ["XAUUSD.0", "XAUUSD"],
    "GBPUSD": ["GBPUSD.0", "GBPUSD"],
    "BTCUSD": ["BTCUSD.0", "BTCUSD"],
    "EURUSD": ["EURUSD.0", "EURUSD"],
    "US30": ["Wall Street 30.0", "US30"],
    "NAS100": ["US Tech 100.0", "NAS100"],
}


def main():

    settings = load_settings()

    requested_symbols = settings["market"]["instruments"]
    timeframes = list(settings["market"]["timeframes"].keys())

    candle_count = int(
        settings["market"]["candles_per_timeframe"]
    )

    execution_enabled = settings["trading"]["execution_enabled"]

    market = MarketData()
    validator = CandleValidator()
    connection = MT5Connection()

    results = []

    try:

        terminal, account = connection.connect()

        print("\n=== DERIV / MT5 ACCOUNT CHECK ===")

        print(f"Terminal: {terminal.name}")
        print(f"Company:  {account.company}")
        print(f"Server:   {account.server}")
        print(f"Login:    {account.login}")
        print(f"Currency: {account.currency}")
        print(f"Balance:  {account.balance}")
        print(f"Equity:   {account.equity}")

        print(f"Trading execution enabled: {execution_enabled}")

        available = market.discover_symbols()

        print(
            f"\nBroker symbols discovered: {len(available)}"
        )

        print("\n=== INSTRUMENT DISCOVERY ===")

        resolved = {}

    for requested in requested_symbols:

         candidates = SYMBOL_CANDIDATES.get(
                requested,
                [requested]
            )

         actual = None

    for candidate in candidates:

                actual = market.resolve_symbol(
                    candidate,
                    available
                )

                if actual:
                    break

                if actual is None:

                 print(
                    f"[NOT FOUND] {requested} - "
                    "check Deriv Market Watch / symbol suffix."
                )

                possible_matches = [
                    symbol for symbol in available
                    if requested.upper() in symbol.upper()
                ]

                if possible_matches:

                    print(
                        f"  Possible matches: "
                        f"{', '.join(possible_matches[:10])}"
                    )

                for timeframe in timeframes:

                    results.append({
                        "instrument": requested,
                        "timeframe": timeframe,
                        "status": "FAIL",
                        "candles": 0,
                        "details": "Broker symbol not found."
                    })

                continue

    info = market.enable_symbol(actual)

    resolved[requested] = actual

    print(
                f"[FOUND] {requested} -> {actual} | "
                f"digits={info.digits} | "
                f"point={info.point} | "
                f"trade_mode={info.trade_mode} | "
                f"volume_min={info.volume_min} | "
                f"volume_step={info.volume_step}"
            )