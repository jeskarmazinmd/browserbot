"""Allow a deleted research source to disappear without silencing frozen leaves."""
import importlib


def optional_source(name):
    qualified = f"strategies.{name}"
    try:
        return importlib.import_module(qualified)
    except ModuleNotFoundError as exc:
        if exc.name != qualified:
            raise
        return None
