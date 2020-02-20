import json
import os

import pytest

from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import AliceConfiguration, BobConfiguration, UrsulaConfiguration
from nucypher.config.constants import NUCYPHER_ENVVAR_KEYRING_PASSWORD, NUCYPHER_ENVVAR_WORKER_IP_ADDRESS
from nucypher.utilities.sandbox.constants import (
    TEMPORARY_DOMAIN,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_IP_ADDRESS,
    TEST_PROVIDER_URI
)

CONFIG_CLASSES = (AliceConfiguration, BobConfiguration, UrsulaConfiguration)


ENV = {NUCYPHER_ENVVAR_WORKER_IP_ADDRESS: MOCK_IP_ADDRESS,
       NUCYPHER_ENVVAR_KEYRING_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}


@pytest.mark.parametrize('config_class', CONFIG_CLASSES)
def test_initialize_via_cli(config_class, custom_filepath, click_runner, monkeypatch):
    command = config_class.CHARACTER_CLASS.__name__.lower()

    # Use a custom local filepath for configuration
    init_args = (command, 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only',
                 '--config-root', custom_filepath)

    user_input = '{password}\n{password}'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input, catch_exceptions=False, env=ENV)
    assert result.exit_code == 0

    # CLI Output
    assert MOCK_CUSTOM_INSTALLATION_PATH in result.output, "Configuration not in system temporary directory"

    # Files and Directories
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'keyring')), 'Keyring does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'known_nodes')), 'known_nodes directory does not exist'


@pytest.mark.parametrize('config_class', CONFIG_CLASSES)
def test_reconfigure_via_cli(click_runner, custom_filepath, config_class):
    custom_config_filepath = os.path.join(custom_filepath, config_class.generate_filename())

    view_args = (config_class.CHARACTER_CLASS.__name__.lower(), 'config',
                 '--config-file', custom_config_filepath,
                 '--debug')

    result = click_runner.invoke(nucypher_cli, view_args, env=ENV)
    assert result.exit_code == 0, result.output

    # Ensure all config fields are displayed
    config = config_class.from_configuration_file(custom_config_filepath)
    analog_payload = json.loads(config.serialize())
    for field in analog_payload:
        assert field in result.output

    # Read pre-edit state
    config = config_class.from_configuration_file(custom_config_filepath)
    assert config.federated_only
    assert config.provider_uri != TEST_PROVIDER_URI
    del config

    # Write
    view_args = (config_class.CHARACTER_CLASS.__name__.lower(), 'config',
                 '--config-file', custom_config_filepath,
                 '--decentralized',
                 '--provider', TEST_PROVIDER_URI)
    result = click_runner.invoke(nucypher_cli, view_args, env=ENV)
    assert result.exit_code == 0

    # Read again
    config = config_class.from_configuration_file(custom_config_filepath)
    analog_payload = json.loads(config.serialize())
    for field in analog_payload:
        assert field in result.output
    assert custom_filepath in result.output

    # After editing the fields have been updated
    assert not config.federated_only
    assert config.provider_uri == TEST_PROVIDER_URI
