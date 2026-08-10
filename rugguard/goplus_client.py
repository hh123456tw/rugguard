import requests

BSC_CHAIN_ID = "56"
BASE_URL = "https://api.gopluslabs.io/api/v1/token_security/{chain_id}"


class GoPlusClient:
    def __init__(self, chain_id: str = BSC_CHAIN_ID, base_url: str = BASE_URL):
        self.chain_id = chain_id
        self.base_url = base_url

    @staticmethod
    def parse_response(data: dict, token_address: str) -> dict:
        if data.get("code") != 1:
            raise ValueError(data.get("message", "unknown error"))
        result = data.get("result", {})
        if token_address not in result:
            raise ValueError(f"token {token_address} not found in response")
        return result[token_address]

    def fetch_token_security(self, token_address: str) -> dict:
        url = self.base_url.format(chain_id=self.chain_id)
        resp = requests.get(url, params={"contract_addresses": token_address}, timeout=15)
        resp.raise_for_status()
        return self.parse_response(resp.json(), token_address.lower())
