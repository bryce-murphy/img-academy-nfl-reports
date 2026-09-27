"""Exceptions shared by the data, evidence and edition layers."""


class DataError(RuntimeError):
    """A source cannot safely support this edition."""


class NotReady(DataError):
    """Data for the reporting week has not landed yet; a later attempt may succeed."""

    def __init__(self, message, week=None):
        super().__init__(message)
        self.week = week
