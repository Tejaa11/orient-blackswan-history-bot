class BotError(RuntimeError):
    """An operational failure; never convert this into 'Not found'."""


class InputError(ValueError):
    """A question is empty or too long."""

