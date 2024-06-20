import asyncio
import datetime as dt
import random

import aiohttp
from eth_typing import Hash32, HexStr
from hexbytes import HexBytes
from web3 import Web3
from web3.eth import AsyncEth
from web3.types import TxReceipt

from config import config
from logger import logger


async def wait_for_transaction_receipt(
    web3: AsyncEth,
    txn_hash: Hash32 | HexBytes | HexStr,
    timeout: int = 300,
    logging_prefix: str = 'Receipt'
) -> TxReceipt:
    start_time = dt.datetime.now()
    while True:
        try:
            receipt = await web3.wait_for_transaction_receipt(
                transaction_hash=txn_hash,
                timeout=timeout - (dt.datetime.now() - start_time).total_seconds()
            )
        except Exception as e:
            logger.warning(f'[{logging_prefix}] Exception occured while waiting for transaction receipt: {e}')
            if dt.datetime.now() - start_time >= dt.timedelta(seconds=timeout):
                return
            await asyncio.sleep(min(5, timeout / 10))
        else:
            return receipt


async def suggest_gas_fees(
    chain_id: int,
    proxy: str = None
):
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.get(
                url=f'https://gas-api.metaswap.codefi.network/networks/{chain_id}/suggestedGasFees',
                proxy=proxy
            )

            await response.read()
    except Exception as exc:
        logger.warning(f'[Gas] Failed to get gas price for chain with ID {chain_id}: {exc}')
        return
    else:
        if response.status != 200:
            logger.warning(f'[Gas] Failed to get gas price for chain with ID {chain_id}: {await response.text()}')
            return
        else:
            gas_json = await response.json()
            high_gas = gas_json['high']

            return {
                'maxFeePerGas': Web3.to_wei(float(high_gas['suggestedMaxFeePerGas']), 'gwei'),
                'maxPriorityFeePerGas': Web3.to_wei(float(high_gas['suggestedMaxPriorityFeePerGas']), 'gwei')
            }


async def random_sleep():
    sleep_time = round(random.uniform(config.min_sleep_time, config.max_sleep_time), 2)
    logger.info(f'[Sleep] Sleeping for {sleep_time} seconds')
    await asyncio.sleep(sleep_time)
