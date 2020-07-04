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
import types
from os.path import abspath, dirname

import os
from unittest.mock import PropertyMock

import maya
import pytest
from hexbytes import HexBytes

from nucypher.blockchain.eth.clients import EthereumClient
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler, SourceDirs
from nucypher.crypto.powers import TransactingPower
# Prevents TesterBlockchain to be picked up by py.test as a test class
from tests.fixtures import _make_testerchain
from tests.mock.interfaces import MockBlockchain
from tests.utils.blockchain import TesterBlockchain as _TesterBlockchain
from tests.constants import (DEVELOPMENT_ETH_AIRDROP_AMOUNT, INSECURE_DEVELOPMENT_PASSWORD,
                                   NUMBER_OF_ETH_TEST_ACCOUNTS, NUMBER_OF_STAKERS_IN_BLOCKCHAIN_TESTS,
                                   NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS)


@pytest.fixture()
def another_testerchain(solidity_compiler):
    testerchain = _TesterBlockchain(eth_airdrop=True, free_transactions=True, light=True, compiler=solidity_compiler)
    testerchain.deployer_address = testerchain.etherbase_account
    assert testerchain.is_light
    yield testerchain


def test_testerchain_creation(testerchain, another_testerchain):

    chains = (testerchain, another_testerchain)

    for chain in chains:

        # Ensure we are testing on the correct network...
        assert 'tester' in chain.provider_uri

        # ... and that there are already some blocks mined
        chain.w3.eth.web3.testing.mine(1)
        assert chain.w3.eth.blockNumber > 0

        # Check that we have enough test accounts
        assert len(chain.client.accounts) >= NUMBER_OF_ETH_TEST_ACCOUNTS

        # Check that distinguished accounts are assigned
        etherbase = chain.etherbase_account
        assert etherbase == chain.client.accounts[0]

        alice = chain.alice_account
        assert alice == chain.client.accounts[1]

        bob = chain.bob_account
        assert bob == chain.client.accounts[2]

        stakers = [chain.staker_account(i) for i in range(NUMBER_OF_STAKERS_IN_BLOCKCHAIN_TESTS)]
        assert stakers == chain.stakers_accounts

        ursulas = [chain.ursula_account(i) for i in range(NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS)]
        assert ursulas == chain.ursulas_accounts

        # Check that the remaining accounts are different from the previous ones:
        assert set([etherbase, alice, bob] + ursulas + stakers).isdisjoint(set(chain.unassigned_accounts))

        # Check that accounts are funded
        for account in chain.client.accounts:
            assert chain.client.get_balance(account) >= DEVELOPMENT_ETH_AIRDROP_AMOUNT

        # Check that accounts can send transactions
        for account in chain.client.accounts:
            balance = chain.client.get_balance(account)
            assert balance

            tx = {'to': etherbase, 'from': account, 'value': 100}
            txhash = chain.client.send_transaction(tx)
            _receipt = chain.wait_for_receipt(txhash)


def test_multiversion_contract():
    # Prepare compiler
    base_dir = os.path.join(dirname(abspath(__file__)), "contracts", "multiversion")
    v1_dir = os.path.join(base_dir, "v1")
    v2_dir = os.path.join(base_dir, "v2")
    root_dir = SolidityCompiler.default_contract_dir()
    solidity_compiler = SolidityCompiler(source_dirs=[SourceDirs(root_dir, {v2_dir}),
                                                      SourceDirs(root_dir, {v1_dir})])

    # Prepare chain
    blockchain_interface = BlockchainDeployerInterface(provider_uri='tester://pyevm/2', compiler=solidity_compiler)
    blockchain_interface.connect()
    origin = blockchain_interface.client.accounts[0]
    blockchain_interface.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD, account=origin)
    blockchain_interface.transacting_power.activate()

    # Searching both contract through raw data
    contract_name = "VersionTest"
    requested_version = "v1.2.3"
    version, _data = blockchain_interface.find_raw_contract_data(contract_name=contract_name,
                                                                 requested_version=requested_version)
    assert version == requested_version
    version, _data = blockchain_interface.find_raw_contract_data(contract_name=contract_name,
                                                                 requested_version="latest")
    assert version == requested_version

    requested_version = "v1.1.4"
    version, _data = blockchain_interface.find_raw_contract_data(contract_name=contract_name,
                                                                 requested_version=requested_version)
    assert version == requested_version
    version, _data = blockchain_interface.find_raw_contract_data(contract_name=contract_name,
                                                                 requested_version="earliest")
    assert version == requested_version

    # Deploy different contracts and check their versions
    registry = InMemoryContractRegistry()
    contract, receipt = blockchain_interface.deploy_contract(deployer_address=origin,
                                                             registry=registry,
                                                             contract_name=contract_name,
                                                             contract_version="v1.1.4")
    assert contract.version == "v1.1.4"
    assert contract.functions.VERSION().call() == 1
    contract, receipt = blockchain_interface.deploy_contract(deployer_address=origin,
                                                             registry=registry,
                                                             contract_name=contract_name,
                                                             contract_version="earliest")
    assert contract.version == "v1.1.4"
    assert contract.functions.VERSION().call() == 1

    contract, receipt = blockchain_interface.deploy_contract(deployer_address=origin,
                                                             registry=registry,
                                                             contract_name=contract_name,
                                                             contract_version="v1.2.3")
    assert contract.version == "v1.2.3"
    assert contract.functions.VERSION().call() == 2
    contract, receipt = blockchain_interface.deploy_contract(deployer_address=origin,
                                                             registry=registry,
                                                             contract_name=contract_name,
                                                             contract_version="latest")
    assert contract.version == "v1.2.3"
    assert contract.functions.VERSION().call() == 2
    contract, receipt = blockchain_interface.deploy_contract(deployer_address=origin,
                                                             registry=registry,
                                                             contract_name=contract_name)
    assert contract.version == "v1.2.3"
    assert contract.functions.VERSION().call() == 2


def test_block_confirmations(testerchain, test_registry, mocker):
    origin = testerchain.etherbase_account

    # Mocks and test adjustments
    testerchain.TIMEOUT = 5  # Reduce timeout for tests, for the moment
    mocker.patch.object(testerchain.client, '_calculate_confirmations_timeout', return_value=1)
    EthereumClient.BLOCK_CONFIRMATIONS_POLLING_TIME = 0.1
    EthereumClient.COOLING_TIME = 0

    # Let's try to deploy a simple contract (ReceiveApprovalMethodMock) with 1 confirmation.
    # Since the testerchain doesn't mine new blocks automatically, this fails.
    with pytest.raises(EthereumClient.TransactionTimeout):
        _ = testerchain.deploy_contract(origin, test_registry, 'ReceiveApprovalMethodMock', confirmations=1)

    # Trying again with no confirmation succeeds.
    contract, _ = testerchain.deploy_contract(origin, test_registry, 'ReceiveApprovalMethodMock')

    # Trying a simple function of the contract with 1 confirmations fails too, for the same reason
    tx_function = contract.functions.receiveApproval(origin, 0, origin, b'')
    with pytest.raises(EthereumClient.TransactionTimeout):
        _ = testerchain.send_transaction(contract_function=tx_function, sender_address=origin, confirmations=1)

    # Trying again with no confirmation succeeds.
    receipt = testerchain.send_transaction(contract_function=tx_function, sender_address=origin, confirmations=0)
    assert receipt['status'] == 1
