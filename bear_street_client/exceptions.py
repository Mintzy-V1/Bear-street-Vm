class BearStreetAPIError(Exception):
    def __init__(self, message, response_message=None, status_code=None, response_data=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data
        self.response_message = response_message

    def __str__(self):
        base = super().__str__()
        parts = []
        if self.status_code is not None:
            parts.append(f"Status: {self.status_code}")
        if self.response_message:
            parts.append(f"Msg: {self.response_message}")
        if self.response_data:
            parts.append(f"Data: {self.response_data}")
        return f"{base} ({' | '.join(parts)})" if parts else base


class BearStreetAuthError(BearStreetAPIError):
    pass


class BearStreetDataFetchError(BearStreetAPIError):
    pass


class BearStreetInvalidResponseError(BearStreetAPIError):
    pass
