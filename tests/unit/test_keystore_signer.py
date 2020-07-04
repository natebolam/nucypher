"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import collections
import json
import os

import pytest
import shutil
from cytoolz.dicttoolz import assoc
from eth_account import Account
from eth_account._utils.transactions import Transaction
from eth_utils import to_checksum_address
from hexbytes import HexBytes
from pathlib import Path

from nucypher.blockchain.eth.signers import KeystoreSigner, Signer
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD

# Example keystore filename
MOCK_KEYFILE_NAME = 'UTC--2019-12-04T05-39-04.006429310Z--0xdeadbeef'
MOCK_KEYFILE = {'address': '0x13978aee95f38490e9769C39B2773Ed763d9cd5F', 'version': 3}

TRANSACTION_DICT = {
    "chainId": None,
    "nonce": 0,
    "gasPrice": 1000000000000,
    "gas": 10000,
    "to": "0x13978aee95f38490e9769C39B2773Ed763d9cd5F",
    "value": 10000000000000000,
    "data": ""
}


@pytest.fixture(scope='module')
def mock_key():
    test_key = Account.create(extra_entropy='M*A*S*H* DIWOKNECNECENOE#@!')
    return test_key


@pytest.fixture(scope='module')
def mock_account(mock_key):
    account = Account.from_key(private_key=mock_key.privateKey)
    return account


@pytest.fixture(scope='module')
def mock_keystore(mock_account, tmp_path_factory):
    keystore = tmp_path_factory.mktemp('keystore')
    json.dump(
        mock_account.encrypt(INSECURE_DEVELOPMENT_PASSWORD),
        open(keystore / MOCK_KEYFILE_NAME, 'x+t')
    )
    return keystore


@pytest.fixture(scope='function')
def good_signer(mocker, mock_account, mock_keystore):

    # Return a "real" account address from the keyfile
    mock_keystore_path = mock_keystore
    mock_keystore_uri = f'keystore:{mock_keystore}'

    signer = Signer.from_signer_uri(uri=mock_keystore_uri)  # type: KeystoreSigner

    # unlock
    signer.unlock_account(account=mock_account.address, password=INSECURE_DEVELOPMENT_PASSWORD)

    return signer


@pytest.fixture(scope='module')
def unknown_address():
    address = Account.create().address
    return address


def test_blank_keystore_uri():
    with pytest.raises(Signer.InvalidSignerURI, match=
        'Blank signer URI - No keystore path provided') as error:
        Signer.from_signer_uri(uri='keystore://')  # it's blank!


def test_invalid_keystore(mocker, tmp_path):
    with pytest.raises(Signer.InvalidSignerURI) as e:
        Signer.from_signer_uri(uri=f'keystore:{tmp_path/"nonexistent"}')

    empty_path = tmp_path / 'empty_file'
    open(empty_path, 'x+t').close()
    with pytest.raises(KeystoreSigner.InvalidKeyfile, match=
        'Invalid JSON in keyfile at') as e:
        Signer.from_signer_uri(uri=f'keystore:{empty_path}')

    empty_json = tmp_path / 'empty_json'
    json.dump({}, open(empty_json, 'x+t'))
    with pytest.raises(KeystoreSigner.InvalidKeyfile, match=
        'Keyfile does not contain address field at') as e:
        Signer.from_signer_uri(uri=f'keystore:{empty_json}')

    bad_address = tmp_path / 'bad_address'
    json.dump({'address':''}, open(bad_address, 'x+t'))
    with pytest.raises(KeystoreSigner.InvalidKeyfile, match=
        'does not contain a valid ethereum address') as e:
        Signer.from_signer_uri(uri=f'keystore:{bad_address}')


def test_signer_reads_keystore_from_disk(mock_account, mock_key, tmpdir):

    # Test reading a keyfile from the disk via KeystoreSigner since
    # it is mocked for the rest of this test module
    fake_ethereum = Path(tmpdir) / '.fake-ethereum'
    try:
        fake_ethereum.mkdir()

        tmp_keystore = Path(tmpdir) / '.fake-ethereum' / 'keystore'
        tmp_keystore.mkdir()

        mock_keyfile_path = tmp_keystore / MOCK_KEYFILE_NAME
        mock_keyfile_path.touch(exist_ok=True)

        with open(mock_keyfile_path, 'w') as fake_keyfile:
            fake_keyfile.write(json.dumps(MOCK_KEYFILE))

        mock_keystore_uri = f'keystore://{tmp_keystore}'
        signer = Signer.from_signer_uri(uri=mock_keystore_uri)

        assert signer.path == str(tmp_keystore)
        assert len(signer.accounts) == 1
        assert MOCK_KEYFILE['address'] in signer.accounts

    finally:
        if fake_ethereum.exists():
            shutil.rmtree(fake_ethereum, ignore_errors=True)


def test_create_signer_from_directory(mocker, mock_account, mock_keystore):
    mock_keystore_path = mock_keystore
    mock_keystore_uri = f'keystore:{mock_keystore_path}'

    # Return a "real" account address from the keyfile
    signer = Signer.from_signer_uri(uri=mock_keystore_uri)  # type: KeystoreSigner
    assert signer.path == str(mock_keystore_path)
    assert len(signer.accounts) == 1
    assert mock_account.address in signer.accounts


def test_create_signer_from_file(mocker, mock_account, mock_keystore):
    mock_keystore_path = mock_keystore / MOCK_KEYFILE_NAME
    mock_keystore_uri = f'keystore:{mock_keystore_path}'

    # Return a "real" account address from the keyfile
    signer = Signer.from_signer_uri(uri=mock_keystore_uri)  # type: KeystoreSigner
    assert signer.path == str(mock_keystore_path)
    assert len(signer.accounts) == 1
    assert mock_account.address in signer.accounts


def test_keystore_locking(mocker, mock_account, good_signer, unknown_address):

    #
    # Unlock
    #

    with pytest.raises(Signer.UnknownAccount):
        good_signer.unlock_account(account=unknown_address, password=INSECURE_DEVELOPMENT_PASSWORD)

    successful_unlock = good_signer.unlock_account(account=mock_account.address, password=INSECURE_DEVELOPMENT_PASSWORD)
    assert successful_unlock

    #
    # Lock
    #

    with pytest.raises(Signer.UnknownAccount):
        good_signer.lock_account(account=unknown_address)

    successful_lock = good_signer.lock_account(account=mock_account.address)
    assert successful_lock


def test_list_keystore_accounts(good_signer, mock_account):
    tracked_accounts = good_signer.accounts
    assert mock_account.address in tracked_accounts
    assert len(tracked_accounts) == 1


def test_sign_message(mocker, good_signer, mock_account, mock_key):

    # unlock
    mock_decrypt = mocker.patch.object(Account, 'decrypt', autospec=True)
    mock_decrypt.return_value = mock_key.privateKey
    successful_unlock = good_signer.unlock_account(account=mock_account.address, password=INSECURE_DEVELOPMENT_PASSWORD)
    assert successful_unlock

    # sign message
    message = b'A million tiny bubbles exploding'
    signature = good_signer.sign_message(account=mock_account.address, message=message)
    assert len(signature) == 65


def test_sign_transaction(good_signer, mock_account):
    transaction_dict = assoc(TRANSACTION_DICT, 'from', value=mock_account.address)
    signed_transaction = good_signer.sign_transaction(transaction_dict=transaction_dict)
    assert isinstance(signed_transaction, HexBytes)

    # assert valid transaction
    transaction = Transaction.from_bytes(signed_transaction)
    assert to_checksum_address(transaction.to) == transaction_dict['to']
