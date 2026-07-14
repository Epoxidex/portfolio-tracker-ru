"""Privacy-aware construction of the official T-Invest SDK client."""
from .. import config


def make_client(token: str):
    from t_tech.invest import Client

    if not config.TINVEST_SDK_ERROR_REPORTING:
        # t-tech-investments 1.49.x initializes its error-reporting hub from a
        # function imported into clients.py. Disable that optional diagnostic
        # channel before entering Client; API requests themselves are unchanged.
        import t_tech.invest.clients as sdk_clients

        sdk_clients.init_error_hub = lambda _client: None
    return Client(token)
