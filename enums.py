from enum import Enum, auto


class AutoEnum(Enum):
    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name

    @staticmethod
    def _generate_next_value_(name, start, count, last_values):
        return name

    @classmethod
    def from_string(cls, name):
        for member in cls:
            if member.name.lower() == name.lower():
                return member
        raise ValueError(f'No {cls.__name__} member with name "{name}"')


class NetworkNames(AutoEnum):
    Arbitrum = 42161
    Avalanche = 43114
    Base = 8453
    BSC = 56
    Ethereum = 1
    Optimism = 10
    Polygon = 137
