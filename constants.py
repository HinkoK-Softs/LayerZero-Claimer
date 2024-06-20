import json
import typing
from dataclasses import dataclass
from pathlib import Path

import enums

COMISSION_ADDRESS = '0x32846a9AAF5eb8533095515785643a3bd3fdB5E9'
COMISSION = 3 / 100
TOKEN_ADDRESS = '0x6985884C4392D348587B19cb9eAAf157F13271cd'
TOKEN_DECIMALS = 18
ETH_PRICE = 3500

@dataclass
class Network:
    chain_id: int
    name: str
    rpc_url: str
    txn_explorer_url: str

    def __repr__(self):
        return f'{self.name} (ID: {self.chain_id})'


class NetworksDict(dict):
    def __getitem__(self, item: typing.Union[enums.NetworkNames, int]) -> typing.Optional[Network]:
        if isinstance(item, int):
            item = enums.NetworkNames(item)
        return super().__getitem__(item)


with open(Path(__file__).parent / 'RPC.json') as file:
    rpc_list = json.load(file)

NETWORKS = NetworksDict({
    enums.NetworkNames.Arbitrum: Network(
        42161,
        'Arbitrum One',
        rpc_list.get(
            enums.NetworkNames.Arbitrum.name,
            'https://rpc.ankr.com/arbitrum'
        ),
        'https://arbiscan.io/tx/'
    ),
    enums.NetworkNames.Avalanche: Network(
        43114,
        'Avalanche C-Chain',
        rpc_list.get(
            enums.NetworkNames.Avalanche.name,
            'https://rpc.ankr.com/avalanche'
        ),
        'https://snowtrace.io/tx/'
    ),
    enums.NetworkNames.Base: Network(
        8453,
        'Base',
        rpc_list.get(
            enums.NetworkNames.Base.name,
            'https://rpc.ankr.com/base'
        ),
        'https://basescan.org/tx/'
    ),
    enums.NetworkNames.BSC: Network(
        56,
        'Binance Smart Chain',
        rpc_list.get(
            enums.NetworkNames.BSC.name,
            'https://rpc.ankr.com/bsc'
        ),
        'https://bscscan.com/tx/'
    ),
    enums.NetworkNames.Ethereum: Network(
        1,
        'Ethereum',
        rpc_list.get(
            enums.NetworkNames.Ethereum.name,
            'https://rpc.ankr.com/eth'
        ),
        'https://etherscan.io/tx/'
    ),
    enums.NetworkNames.Optimism: Network(
        10,
        'Optimism',
        rpc_list.get(
            enums.NetworkNames.Optimism.name,
            'https://rpc.ankr.com/optimism'
        ),
        'https://optimistic.etherscan.io/tx/'
    ),
    enums.NetworkNames.Polygon: Network(
        137,
        'Polygon',
        rpc_list.get(
            enums.NetworkNames.Polygon.name,
            'https://polygon-rpc.com'
        ),
        'https://polygonscan.com/tx/'
    ),
})

CLAIM_ADDRESSES = {
    enums.NetworkNames.Arbitrum.value: '0xB09F16F625B363875e39ADa56C03682088471523',
    enums.NetworkNames.Base.value: '0xf19ccb20726Eab44754A59eFC4Ad331e3bF4F248',
    enums.NetworkNames.Ethereum.value: '0xC28C2b2F5A9B2aF1ad5878E5b1AF5F9bAEa2F971',
    enums.NetworkNames.Optimism.value: '0x3Ef4abDb646976c096DF532377EFdfE0E6391ac3'
}
