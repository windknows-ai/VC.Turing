"""API keys live in Windows Credential Manager (via keyring), never in config files."""

import os

SERVICE = "Turing"


def get_api_key(provider: str) -> str | None:
    env = os.environ.get(f"TURING_{provider.upper()}_API_KEY")
    if env:
        return env
    try:
        import keyring

        return keyring.get_password(SERVICE, provider)
    except Exception:
        return None


def set_api_key(provider: str, key: str) -> None:
    import keyring

    if key:
        keyring.set_password(SERVICE, provider, key)
    else:
        delete_api_key(provider)


def delete_api_key(provider: str) -> None:
    import keyring

    try:
        keyring.delete_password(SERVICE, provider)
    except keyring.errors.PasswordDeleteError:
        pass
