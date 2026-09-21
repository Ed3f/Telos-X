import re
import time
from typing import Any, Optional

import requests


URL_REGEX = re.compile(
    r"https?://[^\s<>'\"]+",
    re.IGNORECASE,
)


def check_host(
    message: str,
) -> Optional[Any]:

    match = URL_REGEX.search(
        message or ""
    )

    if not match:
        return None

    host = match.group(0).rstrip(
        ".,);]}>"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(X11; Linux x86_64) "
            "Telos-X/1.0"
        ),
        "Accept": "application/json",
    }

    try:
        response = requests.get(
            "https://check-host.net/check-http",
            params={"host": host},
            headers=headers,
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        request_id = data.get(
            "request_id"
        )

        if not request_id:
            return None

        result_url = (
            "https://check-host.net/check-result/"
            + str(request_id)
        )

        # Poll limitato.
        for _ in range(4):
            time.sleep(3)

            result_response = requests.get(
                result_url,
                headers=headers,
                timeout=15,
            )

            result_response.raise_for_status()

            result = result_response.json()

            if result:
                return result

        return None

    except (
        requests.RequestException,
        ValueError,
        KeyError,
    ):
        return None