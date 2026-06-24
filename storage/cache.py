from __future__ import annotations

from functools import wraps
from time import time

import pandas as pd

_DF_CACHE: dict[tuple, tuple[float, pd.DataFrame]] = {}


def cache_dataframe(ttl_seconds: int = 300):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (func.__name__, args, tuple(sorted(kwargs.items())))
            now = time()
            if key in _DF_CACHE:
                created, df = _DF_CACHE[key]
                if now - created <= ttl_seconds:
                    return df.copy()
            df = func(*args, **kwargs)
            _DF_CACHE[key] = (now, df.copy() if isinstance(df, pd.DataFrame) else df)
            return df.copy() if isinstance(df, pd.DataFrame) else df

        return wrapper

    return decorator
