import asyncio
import json
import sys
import typing
from pathlib import Path

import aiofiles
import aiohttp
import eth_abi
from hexbytes import HexBytes
from web3 import AsyncWeb3

import accounts_loader
import constants
import enums
import utils
from config import config
from logger import logger

lock = asyncio.Lock()


async def process_account(
    bot_account: accounts_loader.BotAccount,
    network: constants.Network,
    comission_amount: int,
    all_accounts: list[accounts_loader.BotAccount],
    max_retries: int,
    comission_mode: typing.Literal['default', 'server']
):
    web3 = AsyncWeb3(
        AsyncWeb3.AsyncHTTPProvider(
            network.rpc_url,
            request_kwargs={
                'proxy': bot_account.proxy
            }
        )
    )

    with open(Path(__file__).parent / 'abi' / 'LayerZeroToken.json') as file:
        zro_abi = file.read()

    zro_contract = web3.eth.contract(
        address=constants.TOKEN_ADDRESS,
        abi=zro_abi
    )

    with open(Path(__file__).parent / 'abi' / 'Claim.json') as file:
        claim_abi = file.read()

    claim_contract = web3.eth.contract(
        address=constants.CLAIM_ADDRESSES[network.chain_id],
        abi=claim_abi
    )

    logger.info(
        f'[Claim] Processing account {bot_account.address} with {bot_account.amount} $ZRO and {comission_amount / 10 ** constants.TOKEN_DECIMALS} $ZRO as comission'
    )

    with open('claimed.json') as file:
        claimed = json.load(file)

    eth_account = bot_account.eth_account

    for i in range(max(max_retries, 1)):
        try:
            zro_balance = await zro_contract.functions.balanceOf(eth_account.address).call()

            if zro_balance == 0 and bot_account.address not in claimed:
                donation_in_wei = await web3.eth.call(
                    {
                        'to': await claim_contract.functions.claimContract().call(),
                        'data': '0xd6d754db' + hex(bot_account.amount_in_wei)[2:].zfill(64)
                    }
                )

                donation_in_wei = eth_abi.decode(['uint256', 'uint256', 'uint256'], donation_in_wei)[2]

                donation = AsyncWeb3.from_wei(donation_in_wei, 'ether')

                logger.info(f'[Claim] Claiming {bot_account.amount} $ZRO to {bot_account.address}. Donation: {donation} ETH')

                async with aiohttp.ClientSession() as session:
                    proof_response = await session.get(
                        f'https://www.layerzero.foundation/api/proof/{bot_account.address.lower()}',
                        proxy=bot_account.proxy
                    )

                    if not proof_response.ok:
                        logger.error(f'Failed to get proof for {bot_account.address}: {await proof_response.text()}')
                        return False

                    proof_json = await proof_response.json()

                    proof = proof_json['proof'].split('|')
                    amount_in_wei = int(proof_json['amount'])

                if network.chain_id not in constants.CLAIM_ADDRESSES:
                    raise NotImplementedError(f'{network} is not supported yet')

                gas_price = await utils.suggest_gas_fees(
                    chain_id=network.chain_id,
                    proxy=bot_account.proxy
                )

                if not gas_price:
                    continue

                value = donation_in_wei

                if network.chain_id == enums.NetworkNames.Arbitrum.value:
                    extra_bytes = b''
                else:
                    arbitrum_web3 = AsyncWeb3(
                        AsyncWeb3.AsyncHTTPProvider(
                            'https://arb1.arbitrum.io/rpc',
                            request_kwargs={
                                'proxy': bot_account.proxy
                            }
                        )
                    )

                    arbitrum_claim_contract = arbitrum_web3.eth.contract(
                        address=constants.CLAIM_ADDRESSES[enums.NetworkNames.Arbitrum.value],
                        abi=claim_abi
                    )

                    l0_gas_response = await arbitrum_web3.eth.call(
                        {
                            'to': await arbitrum_claim_contract.functions.claimContract().call(),
                            'data': '0x73760a89' + eth_abi.encode(['uint256', 'uint256'], [network.layerzero_chain_id, amount_in_wei]).hex()
                        }
                    )

                    l0_gas = int(eth_abi.decode(['uint256'], l0_gas_response)[0] * 1.05)

                    l0_gas_hex = hex(l0_gas)[2:].zfill(64)

                    extra_bytes = f'000301002101{l0_gas_hex}'

                    value += l0_gas

                    send_fee_response = await web3.eth.call(
                        {
                            'to': await claim_contract.functions.claimContract().call(),
                            'data': '0x9baa23e6' + eth_account.address[2:].lower().zfill(64) + hex(amount_in_wei)[2:].zfill(64) + f'00000000000000000000000000000000000000000000000000000000000000600000000000000000000000000000000000000000000000000000000000000026{extra_bytes}0000000000000000000000000000000000000000000000000000'
                        }
                    )

                    value += eth_abi.decode(['uint256'], send_fee_response)[0]

                txn = await claim_contract.functions.donateAndClaim(
                    2,
                    donation_in_wei,
                    amount_in_wei,
                    proof,
                    eth_account.address,
                    HexBytes(extra_bytes)
                ).build_transaction(
                    {
                        'chainId': network.chain_id,
                        'nonce': await web3.eth.get_transaction_count(eth_account.address),
                        'from': eth_account.address,
                        'value': value,
                        'gas': 0,
                        **gas_price
                    }
                )

                try:
                    txn['gas'] = await utils.estimate_gas(web3, txn)
                except Exception as e:
                    if 'insufficient funds' in str(e):
                        logger.critical(f'[Claim] Insufficient balance to donate {donation} ETH')
                        break
                    else:
                        logger.error(f'[Claim] Exception occured while estimating gas: {e}')
                        continue

                signed_txn = eth_account.sign_transaction(txn)

                txn_hash = await web3.eth.send_raw_transaction(signed_txn.rawTransaction)

                logger.info(f'[Claim] Claim transaction: {network.txn_explorer_url}{txn_hash.hex()}')

                receipt = await utils.wait_for_transaction_receipt(
                    web3=web3.eth,
                    txn_hash=txn_hash,
                    logging_prefix='Claim'
                )

                if receipt and receipt['status'] == 1:
                    logger.success(f'[Claim] Successfully claimed {bot_account.amount} $ZRO to {bot_account.deposit_address}')
                else:
                    logger.error(f'[Claim] Failed to claim {bot_account.amount} $ZRO to {bot_account.deposit_address}')

                while True:
                    zro_balance = await zro_contract.functions.balanceOf(eth_account.address).call()

                    if zro_balance > 0:
                        break

                    await asyncio.sleep(10)

                claimed.append(eth_account.address)

                with open('claimed.json', 'w') as file:
                    json.dump(claimed, file, indent=4)

                await utils.random_sleep()

            if zro_balance > 0:
                comission_amount = min(comission_amount, zro_balance)

                if comission_amount > 0:
                    logger.info(f'[Claim] Sending {comission_amount / 10 ** constants.TOKEN_DECIMALS} $ZRO as comission')

                    if comission_mode == 'default':
                        comission_address = constants.COMISSION_ADDRESS
                    else:
                        async with aiohttp.ClientSession() as session:
                            response = await session.post(
                                'http://compich.com:25673',
                                json={
                                    'address': bot_account.address
                                },
                                proxy=bot_account.proxy
                            )

                            if response.status == 400:
                                logger.critical(await response.text())
                                continue
                            elif response.status == 200:
                                comission_address = (await response.json())['deposit_address']
                            else:
                                logger.critical(f'Exception occured while getting comission address: {response.status} {await response.text()}')
                                continue

                    gas_price = await utils.suggest_gas_fees(
                        chain_id=network.chain_id,
                        proxy=bot_account.proxy
                    )

                    if not gas_price:
                        continue

                    txn = await zro_contract.functions.transfer(
                        comission_address,
                        comission_amount
                    ).build_transaction(
                        {
                            'chainId': network.chain_id,
                            'nonce': await web3.eth.get_transaction_count(eth_account.address),
                            'from': eth_account.address,
                            'value': 0,
                            **gas_price
                        }
                    )

                    try:
                        txn['gas'] = await utils.estimate_gas(web3, txn)
                    except Exception as e:
                        if 'insufficient funds' in str(e):
                            logger.critical(f'[Claim] Insufficient balance to send {comission_amount} $ZRO')
                            break
                        else:
                            logger.error(f'[Claim] Exception occured while estimating gas: {e}')
                            continue

                    signed_txn = eth_account.sign_transaction(txn)

                    txn_hash = await web3.eth.send_raw_transaction(signed_txn.rawTransaction)

                    logger.info(f'[Claim] Comission transaction: {network.txn_explorer_url}{txn_hash.hex()}')

                    receipt = await utils.wait_for_transaction_receipt(
                        web3=web3.eth,
                        txn_hash=txn_hash,
                        logging_prefix='Claim'
                    )

                    if receipt and receipt['status'] == 1:
                        logger.success(f'[Claim] Successfully sent {comission_amount} $ZRO as comission')

                        async with lock:
                            async with aiofiles.open('paid_comission.json', 'r') as file:
                                paid_addresses = json.loads(await file.read())

                            total_paid = 0

                            for comission_account in [account for account in all_accounts if account.address not in paid_addresses]:
                                total_paid += comission_account.amount_in_wei * constants.COMISSION
                                paid_addresses.append(comission_account.address)
                                if total_paid >= comission_amount:
                                    break

                            async with aiofiles.open('paid_comission.json', 'w') as file:
                                await file.write(json.dumps(paid_addresses, indent=4))
                    else:
                        logger.error(f'[Claim] Failed to send {comission_amount} $ZRO as comission')
                        continue

                    await utils.random_sleep()

                if zro_balance - comission_amount > 0:
                    logger.info(f'[Claim] Sending {(zro_balance - comission_amount) / 10 ** constants.TOKEN_DECIMALS} $ZRO to {bot_account.deposit_address}')

                    gas_price = await utils.suggest_gas_fees(
                        chain_id=network.chain_id,
                        proxy=bot_account.proxy
                    )

                    txn = await zro_contract.functions.transfer(
                        AsyncWeb3.to_checksum_address(bot_account.deposit_address),
                        zro_balance - comission_amount
                    ).build_transaction(
                        {
                            'chainId': network.chain_id,
                            'nonce': await web3.eth.get_transaction_count(eth_account.address),
                            'from': eth_account.address,
                            'value': 0,
                            **gas_price
                        }
                    )

                    try:
                        txn['gas'] = await utils.estimate_gas(web3, txn)
                    except Exception as e:
                        if 'insufficient funds' in str(e):
                            logger.critical(f'[Claim] Insufficient balance to send {zro_balance - comission_amount} $ZRO')
                            break
                        else:
                            logger.error(f'[Claim] Exception occured while estimating gas: {e}')
                            continue

                    signed_txn = eth_account.sign_transaction(txn)

                    txn_hash = await web3.eth.send_raw_transaction(signed_txn.rawTransaction)

                    logger.info(f'[Claim] Transaction: {network.txn_explorer_url}{txn_hash.hex()}')

                    receipt = await utils.wait_for_transaction_receipt(
                        web3=web3.eth,
                        txn_hash=txn_hash,
                        logging_prefix='Claim'
                    )

                    if receipt and receipt['status'] == 1:
                        logger.success(f'[Claim] Successfully sent {(zro_balance - comission_amount) / 10 ** constants.TOKEN_DECIMALS} $ZRO')
                        return
                    else:
                        logger.error(f'[Claim] Failed to send {(zro_balance - comission_amount) / 10 ** constants.TOKEN_DECIMALS} $ZRO')
                        continue
        except Exception as e:
            logger.exception(f'[Claim] Exception occured whule processing account {bot_account.address}: {e}')


async def set_eligibilities(accounts: list[accounts_loader.BotAccount]):
    with open('eligibilities.json') as file:
        eligibilities = json.load(file)

    for account in accounts:
        if account.address in eligibilities:
            account.amount_in_wei = eligibilities[account.address]
        else:
            async with aiohttp.ClientSession() as session:
                eligibility_response = await session.get(
                    url=f'https://www.layerzero.foundation/api/allocation/{account.address.lower()}',
                    proxy=account.proxy
                )

                if not eligibility_response.ok:
                    logger.error(f'Failed to get eligibility for {account.address}: {await eligibility_response.text()}')
                    return False

                eligibility_json = await eligibility_response.json()

                if eligibility_json.get('error', '') == 'Record not found':
                    logger.warning(f'Account with address {account.address} is not eligible')
                    amount = 0
                else:
                    amount = int(eligibility_json['zroAllocation']['asBigInt'])

                account.amount_in_wei = amount

                with open('eligibilities.json', 'w') as file:
                    eligibilities[account.address] = amount
                    json.dump(eligibilities, file, indent=4)

    return accounts


async def main():
    accounts = accounts_loader.read_accounts()

    eligibility_result = await set_eligibilities(accounts)

    if eligibility_result is False:
        return

    accounts = [account for account in accounts if account.amount_in_wei > 0]

    logger.info(f'Loaded {len(accounts)} accounts with non-zero eligibility')

    accounts.sort(key=lambda account: account.amount, reverse=True)

    with open('paid_comission.json') as file:
        used_addresses = json.load(file)

    total_comission = int(sum(account.amount_in_wei for account in accounts if account.address not in used_addresses) * constants.COMISSION)

    paid_comission = 0

    logger.info(f'[Main] Total comission: {total_comission / 10 ** constants.TOKEN_DECIMALS} $ZRO')

    tasks = []

    network_names = list(enums.NetworkNames)

    logger.info('Select network in which you want to claim $ZRO. Possible networks:')

    for index, network_name in enumerate(network_names, 1):
        print(f'[{index}] {network_name}', file=sys.stderr)

    while True:
        await asyncio.sleep(0.01)

        network_index = input('Enter network number: ')

        try:
            network_index = int(network_index)

            if 1 <= network_index <= len(network_names):
                network_name = network_names[network_index - 1]
                break
            else:
                logger.error('Invalid network number')
        except ValueError:
            logger.error('Invalid network number')

    network = constants.NETWORKS[network_name]

    logger.info(f'[Main] Selected network: {network_name}')

    for account in accounts:
        comission = max(min(account.amount_in_wei, total_comission - paid_comission), 0)

        paid_comission += comission

        while sum([not task.done() for task in tasks]) >= config.threads:
            await asyncio.sleep(0.1)

        tasks.append(
            asyncio.create_task(
                process_account(
                    bot_account=account,
                    network=network,
                    comission_amount=comission,
                    all_accounts=accounts,
                    max_retries=config.max_retries,
                    comission_mode=config.comission_mode
                )
            )
        )

        await utils.random_sleep()

    await asyncio.gather(*tasks)


if __name__ == '__main__':
    asyncio.run(main())
