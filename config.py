import json
import typing

from pydantic import BaseModel


class Config(BaseModel):
    threads: int
    max_retries: int
    comission_mode: typing.Literal['default', 'server']
    min_sleep_time: float
    max_sleep_time: float

    @classmethod
    def load(cls):
        with open('config.json') as file:
            data = json.load(file)

        return cls.parse_obj(data)


config = Config.load()
