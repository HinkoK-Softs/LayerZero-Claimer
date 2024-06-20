import dataclasses
import json
import re
import warnings
from pathlib import Path

import pandas as pd
from eth_account import Account
from eth_account.signers.local import LocalAccount

import constants
from logger import logger

def shorten_private_key(private_key: str) -> str:
    if len(private_key) <= 16:
        return private_key
    return f'{private_key[:8]}...{private_key[-8:]}'


@dataclasses.dataclass
class BotAccount:
    private_key: str
    proxy: str
    deposit_address: str
    amount_in_wei: int = None

    @property
    def short_private_key(self):
        return shorten_private_key(self.private_key)

    @property
    def eth_account(self) -> LocalAccount:
        return Account.from_key(self.private_key)

    @property
    def address(self) -> str:
        return self.eth_account.address

    @property
    def amount(self):
        return self.amount_in_wei / 10 ** constants.TOKEN_DECIMALS


def read_accounts() -> list[BotAccount]:
    warnings.filterwarnings(
        'ignore',
        category=UserWarning,
        module='openpyxl'
    )

    logger.info('[Account Loader] Loading accounts')

    with open('eligibilities.json') as file:
        eligibilities = json.load(file)

    accounts = []

    default_account_values = {}
    for field in dataclasses.fields(BotAccount):
        if field.default != dataclasses.MISSING:
            default_account_values[field.name] = field.default

    acounts_file_path = Path(__file__).parent / 'wallets.xlsx'

    if not acounts_file_path.exists():
        logger.error(f'[Account Loader] File "{acounts_file_path.name}" does not exist')
        return False

    accounts_file = pd.ExcelFile(acounts_file_path)
    sheets = [sheet.lower() for sheet in accounts_file.sheet_names]
    del accounts_file

    dtypes = {
        'Private key': str,
        'Proxy': str,
        'Deposit address': str
    }

    accounts_df = pd.read_excel(
        acounts_file_path,
        dtype=dtypes
    )
    accounts_df = accounts_df.apply(lambda x: x.str.strip() if x.dtype == object else x)
    accounts_df.columns = ['_'.join(column.lower().split(' ')) for column in accounts_df.columns]
    unknown_account_columns = set(accounts_df.columns) - {field.name for field in dataclasses.fields(BotAccount)}

    if unknown_account_columns:
        logger.error(f'[Account Loader] Unknown account columns: {", ".join(unknown_account_columns)}')
        return False

    accounts_df.dropna(subset=['private_key'], inplace=True, how='all')

    for column in accounts_df.columns:
        if column in default_account_values:
            accounts_df[column] = accounts_df[column].fillna(
                default_account_values[column]
            )
        else:
            accounts_df[column] = accounts_df[column].fillna(-31294912).replace(-31294912, None)

    for row in accounts_df.itertuples():
        if not row.deposit_address:
            logger.error(f'[Account Loader] Missing deposit address on row {row.Index + 1}')
            return False
        elif not re.match(r'^(0x)?[a-fA-F0-9]+$', row.private_key):
            short_private_key = shorten_private_key(row.private_key)
            logger.error(f'[Account Loader] Invalid private key "{short_private_key}" on row {row.Index + 1}')
            return False

        if row.proxy:
            if re.match(r'(socks5|http)://', row.proxy):
                proxy = row.proxy
            elif '/' not in row.proxy:
                proxy = f'http://{row.proxy}'
            else:
                logger.error(f'[Account Loader] Invalid proxy "{row.proxy}"')
                return False
        else:
            proxy = None

        try:
            account = BotAccount(
                private_key=row.private_key,
                proxy=proxy,
                deposit_address=row.deposit_address
            )
        except AttributeError as e:
            res = re.search("has no attribute '(?P<attribute>.+)'", str(e))
            if res:
                attribute = res.group('attribute')
                logger.error(f'[Account Loader] Missing {attribute} column')
            else:
                logger.error(f'[Account Loader] Failed to load account: {e}')
            return
        accounts.append(account)

    return accounts
